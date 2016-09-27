# from django import forms
from django.core.exceptions import (
    ImproperlyConfigured,
)
from django.forms.formsets import formset_factory
from django.forms.models import (
    BaseModelFormSet, BaseInlineFormSet, ModelChoiceField
)
from django.forms.widgets import HiddenInput
from rest_admin.utils import patch
from rest_admin.forms.resources import RestForm, restform_factory


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


class ResourceChoiceField(ModelChoiceField):
    def validate(self, value):
        return super(ResourceChoiceField, self).validate(value)


class BaseInlineRestFormSet(BaseInlineFormSet):
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
        super(BaseInlineFormSet, self).__init__(data, files, prefix=prefix,
                                                queryset=qs, **kwargs)

    def _construct_form(self, i, **kwargs):
        form = super(BaseInlineFormSet, self)._construct_form(i, **kwargs)
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

    def add_fields(self, form, index):
        from restorm.fields import ToOneField
        with patch('django.db.models.ForeignKey', ToOneField):
            with patch('django.forms.models.ModelChoiceField', ResourceChoiceField):
                result = super(BaseInlineRestFormSet, self).add_fields(form, index)
        return result


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


class BaseRestFormSet(BaseModelFormSet):
    def add_fields(self, form, index):
        """Add a hidden field for the object's primary key."""
        from django.db.models import AutoField
        from restorm.fields import ToOneField
        self._pk_field = pk = self.model._meta.pk
        # If a pk isn't editable, then it won't be on the form, so we need to
        # add it here so we can tell which object is which when we get the
        # data back. Generally, pk.editable should be false, but for some
        # reason, auto_created pk fields and AutoField's editable attribute is
        # True, so check for that as well.

        def pk_is_not_editable(pk):
            return ((not pk.editable) or (pk.auto_created or isinstance(pk, AutoField))
                or (pk.rel and pk.rel.parent_link and pk_is_not_editable(pk.rel.to._meta.pk)))
        if pk_is_not_editable(pk) or pk.name not in form.fields:
            if form.is_bound:
                # If we're adding the related instance, ignore its primary key
                # as it could be an auto-generated default which isn't actually
                # in the database.
                pk_value = None if form.instance._state.adding else form.instance.pk
            else:
                try:
                    if index is not None:
                        pk_value = self.get_queryset()[index].pk
                    else:
                        pk_value = None
                except IndexError:
                    pk_value = None
            if isinstance(pk, ToOneField):
                qs = pk.rel.to._default_manager.get_queryset()
            else:
                qs = self.model._default_manager.get_queryset()
            qs = qs.using(form.instance._state.db)
            if form._meta.widgets:
                widget = form._meta.widgets.get(self._pk_field.name, HiddenInput)
            else:
                widget = HiddenInput
            form.fields[self._pk_field.name] = ModelChoiceField(qs, initial=pk_value, required=False, widget=widget)
        super(BaseModelFormSet, self).add_fields(form, index)


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
