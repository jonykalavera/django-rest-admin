# from django import forms
from django.core.exceptions import (
    ImproperlyConfigured,
)
from django.forms.formsets import formset_factory
from django.forms.models import (
    BaseModelFormSet, BaseInlineFormSet, InlineForeignKeyField, capfirst
)
from django.forms.widgets import HiddenInput
from rest_admin.utils import patch
from rest_admin.forms.resources import RestForm, restform_factory
from rest_admin.forms.fields import ResourceChoiceField


def _get_foreign_key(parent_model, model, fk_name=None, can_fail=False):
    """
    Finds and returns the ForeignKey from model to parent if there is one
    (returns None if can_fail is True and no such field exists). If fk_name is
    provided, assume it is the name of the ForeignKey field. Unless can_fail is
    True, an exception is raised if there is no ForeignKey from model to
    parent_model.
    """
    # avoid circular import
    from restorm.fields import ToOneField
    opts = model._meta
    if fk_name:
        fks_to_parent = [f for f in opts.fields if f.name == fk_name]
        if len(fks_to_parent) == 1:
            fk = fks_to_parent[0]
            if not isinstance(fk, ToOneField) or \
                    (fk.rel.to != parent_model and
                     fk.rel.to not in parent_model._meta.get_parent_list()):
                raise ValueError(
                    "fk_name '%s' is not a ToOneField to '%s.%s'."
                    % (fk_name, parent_model._meta.app_label, parent_model._meta.object_name))
        elif len(fks_to_parent) == 0:
            raise ValueError(
                "'%s.%s' has no field named '%s'."
                % (model._meta.app_label, model._meta.object_name, fk_name))
    else:
        # Try to discover what the ForeignKey from model to parent_model is
        fks_to_parent = [
            f for f in opts.fields
            if isinstance(f, ToOneField)
            and (f.rel.to == parent_model
                or f.rel.to in parent_model._meta.get_parent_list())
        ]
        if len(fks_to_parent) == 1:
            fk = fks_to_parent[0]
        elif len(fks_to_parent) == 0:
            if can_fail:
                return
            raise ValueError(
                "'%s.%s' has no ToOneField to '%s.%s'." % (
                    model._meta.app_label,
                    model._meta.object_name,
                    parent_model._meta.app_label,
                    parent_model._meta.object_name,
                )
            )
        else:
            raise ValueError(
                "'%s.%s' has more than one ToOneField to '%s.%s'." % (
                    model._meta.app_label,
                    model._meta.object_name,
                    parent_model._meta.app_label,
                    parent_model._meta.object_name,
                )
            )
    return fk


class BaseRestFormSet(BaseModelFormSet):
    def add_fields(self, form, index):
        from restorm.fields import ToOneField
        with patch('django.db.models.ForeignKey', ToOneField):
            with patch('django.forms.models.ModelChoiceField', ResourceChoiceField):
                result = super(BaseRestFormSet, self).add_fields(form, index)
        return result

    def _existing_object(self, pk):
        if not hasattr(self, '_object_dict'):
            self._object_dict = {unicode(o.pk): o for o in self.get_queryset()}
        return self._object_dict.get(unicode(pk))

    # def _construct_form(self, i, **kwargs):
    #     if self.is_bound and i < self.initial_form_count():
    #         pk_key = "%s-%s" % (self.add_prefix(i), self.model._meta.pk.name)
    #         pk = self.data[pk_key]
    #         pk_field = self.model._meta.pk
    #         to_python = self._get_to_python(pk_field)
    #         pk = to_python(pk)
    #         kwargs['instance'] = self._existing_object(pk)
    #     if i < self.initial_form_count() and 'instance' not in kwargs:
    #         kwargs['instance'] = self.get_queryset()[i]
    #     if i >= self.initial_form_count() and self.initial_extra:
    #         # Set initial values for extra forms
    #         try:
    #             kwargs['initial'] = self.initial_extra[i - self.initial_form_count()]
    #         except IndexError:
    #             pass
    #     return super(BaseModelFormSet, self)._construct_form(i, **kwargs)


def restformset_factory(model, form=RestForm, formfield_callback=None,
                        formset=BaseRestFormSet, extra=1, can_delete=False,
                        can_order=False, max_num=None, fields=None, exclude=None,
                        widgets=None, validate_max=False, localized_fields=None,
                        labels=None, help_texts=None, error_messages=None,
                        min_num=None, validate_min=False):
    """
    Returns a FormSet class for the given Django model class.
    """
    meta = getattr(form, 'Meta', None)
    if meta is None:
        meta = type(str('Meta'), (object,), {})
    if (getattr(meta, 'fields', fields) is None and
            getattr(meta, 'exclude', exclude) is None):
        raise ImproperlyConfigured(
            "Calling modelformset_factory without defining 'fields' or "
            "'exclude' explicitly is prohibited."
        )

    form = restform_factory(model, form=form, fields=fields, exclude=exclude,
                            formfield_callback=formfield_callback,
                            widgets=widgets, localized_fields=localized_fields,
                            labels=labels, help_texts=help_texts,
                            error_messages=error_messages)
    FormSet = formset_factory(form, formset, extra=extra, min_num=min_num, max_num=max_num,
                              can_order=can_order, can_delete=can_delete,
                              validate_min=validate_min, validate_max=validate_max)
    FormSet.model = model
    return FormSet


class BaseInlineRestFormSet(BaseRestFormSet):
    def __init__(self, data=None, files=None, instance=None,
                 save_as_new=False, prefix=None, queryset=None, **kwargs):
        if instance is None:
            self.instance = self.fk.rel.to()
        else:
            self.instance = instance
        self.save_as_new = save_as_new
        if queryset is None:
            queryset = self.model._default_manager
        if self.instance.pk is not None:
            qs = queryset.filter(**{self.fk.name: self.instance.pk})
        else:
            qs = queryset.none()
        super(BaseInlineRestFormSet, self).__init__(
            data, files, prefix=prefix, queryset=qs, **kwargs)

    def initial_form_count(self):
        if self.save_as_new:
            return 0
        return super(BaseInlineRestFormSet, self).initial_form_count()

    def _construct_form(self, i, **kwargs):
        form = super(BaseInlineRestFormSet, self)._construct_form(i, **kwargs)
        if self.save_as_new:
            # Remove the primary key from the form's data, we are only
            # creating new instances
            form.data[form.add_prefix(self._pk_field.name)] = None

            # Remove the foreign key from the form's data
            form.data[form.add_prefix(self.fk.name)] = None

        # Set the fk value here so that the form can do its validation.
        fk_value = self.instance.pk
        if self.fk.rel.field_name != self.fk.rel.to._meta.pk.name:
            fk_value = getattr(self.instance, self.fk.rel.field_name)
            fk_value = getattr(fk_value, 'pk', fk_value)
        setattr(form.instance, self.fk.get_attname(), fk_value)
        return form

    @classmethod
    def get_default_prefix(cls):
        return cls.fk.rel.get_accessor_name(model=cls.model).replace('+', '')

    def save_new(self, form, commit=True):
        # Ensure the latest copy of the related instance is present on each
        # form (it may have been saved after the formset was originally
        # instantiated).
        setattr(form.instance, self.fk.name, self.instance)
        # Use commit=False so we can assign the parent key afterwards, then
        # save the object.
        obj = form.save(commit=False)
        pk_value = getattr(self.instance, self.fk.rel.field_name)
        setattr(obj, self.fk.get_attname(), getattr(pk_value, 'pk', pk_value))
        if commit:
            obj.save()
        # form.save_m2m() can be called via the formset later on if commit=False
        if commit and hasattr(form, 'save_m2m'):
            form.save_m2m()
        return obj

    def add_fields(self, form, index):
        super(BaseInlineRestFormSet, self).add_fields(form, index)
        if self._pk_field == self.fk:
            name = self._pk_field.name
            kwargs = {'pk_field': True}
        else:
            # The foreign key field might not be on the form, so we poke at the
            # Model field to get the label, since we need that for error messages.
            name = self.fk.name
            kwargs = {
                'label': getattr(form.fields.get(name), 'label', capfirst(self.fk.verbose_name))
            }
            if self.fk.rel.field_name != self.fk.rel.to._meta.pk.name:
                kwargs['to_field'] = self.fk.rel.field_name

        # If we're adding a new object, ignore a parent's auto-generated key
        # as it will be regenerated on the save request.
        if self.instance._state.adding:
            if kwargs.get('to_field') is not None:
                to_field = self.instance._meta.get_field(kwargs['to_field'])
            else:
                to_field = self.instance._meta.pk
            if to_field.has_default():
                setattr(self.instance, to_field.attname, None)

        form.fields[name] = InlineForeignKeyField(self.instance, **kwargs)

        # Add the generated field to form._meta.fields if it's defined to make
        # sure validation isn't skipped on that field.
        if form._meta.fields:
            if isinstance(form._meta.fields, tuple):
                form._meta.fields = list(form._meta.fields)
            form._meta.fields.append(self.fk.name)

    def get_unique_error_message(self, unique_check):
        unique_check = [field for field in unique_check if field != self.fk.name]
        return super(BaseInlineRestFormSet, self).get_unique_error_message(unique_check)


def inlinerestformset_factory(
        parent_model, model, form=RestForm,
        formset=BaseInlineRestFormSet, fk_name=None,
        fields=None, exclude=None, extra=3, can_order=False,
        can_delete=True, max_num=None, formfield_callback=None,
        widgets=None, validate_max=False, localized_fields=None,
        labels=None, help_texts=None, error_messages=None,
        min_num=None, validate_min=False):
    """
    Returns an ``InlineFormSet`` for the given kwargs.
    You must provide ``fk_name`` if ``model`` has more than one ``ForeignKey``
    to ``parent_model``.
    """
    fk = _get_foreign_key(parent_model, model, fk_name=fk_name)
    # enforce a max_num=1 when the foreign key to the parent model is unique.
    if fk.unique:
        max_num = 1
    kwargs = {
        'form': form,
        'formfield_callback': formfield_callback,
        'formset': formset,
        'extra': extra,
        'can_delete': can_delete,
        'can_order': can_order,
        'fields': fields,
        'exclude': exclude,
        'min_num': min_num,
        'max_num': max_num,
        'widgets': widgets,
        'validate_min': validate_min,
        'validate_max': validate_max,
        'localized_fields': localized_fields,
        'labels': labels,
        'help_texts': help_texts,
        'error_messages': error_messages,
    }
    FormSet = restformset_factory(model, **kwargs)
    FormSet.fk = fk
    return FormSet
