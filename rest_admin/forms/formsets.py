# from django import forms
from django.core.exceptions import (
    ImproperlyConfigured,
)
from django.forms.formsets import formset_factory
from django.forms.models import _get_foreign_key as _dj_get_foreign_key
from django.forms.models import (
    BaseModelFormSet, BaseInlineFormSet, InlineForeignKeyField, capfirst
)
from django.forms.widgets import HiddenInput

from rest_admin.utils import patch
from rest_admin.forms.resources import RestForm, restform_factory
from rest_admin.forms.fields import ResourceChoiceField


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


def inlinerestformset_factory(*args, **kwargs):
    from django.forms.models import ModelForm
    from django.forms.models import inlineformset_factory as _dj_inlineformset_factory
    if kwargs.get('form') == ModelForm:
        kwargs['forms'] = RestForm
    with patch('django.forms.models.ModelForm', RestForm):
        with patch('django.forms.models.BaseInlineFormSet', BaseRestFormSet):
            with patch('django.forms.models._get_foreign_key', _get_foreign_key):
                return _dj_inlineformset_factory(*args, **kwargs)


def _get_foreign_key(*args, **kwargs):
    from restorm.fields import ToOneField
    with patch('django.db.models.ForeignKey', ToOneField):
        return _dj_get_foreign_key(*args, **kwargs)
