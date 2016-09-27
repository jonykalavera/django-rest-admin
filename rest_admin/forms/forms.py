# from django import forms
from django.core.exceptions import (
    NON_FIELD_ERRORS, FieldError, ImproperlyConfigured, ValidationError,
)
from django.forms.forms import BaseForm, DeclarativeFieldsMetaclass
from django.forms.formsets import formset_factory
from django.forms.models import (
    ErrorList, ALL_FIELDS, chain, OrderedDict, InlineForeignKeyField,
    BaseModelFormSet, BaseInlineFormSet, ModelChoiceField
)
from django.forms.widgets import HiddenInput
from django.utils import six
from rest_admin.utils import patch


def construct_instance(form, instance, fields=None, exclude=None):
    """
    Constructs and returns a model instance from the bound ``form``'s
    ``cleaned_data``, but does not save the returned instance to the
    database.
    """
    from django.db import models
    opts = instance._meta

    cleaned_data = form.cleaned_data
    file_field_list = []
    for f in opts._fields.values():
        if not f.editable or isinstance(f, models.AutoField) \
                or f.name not in cleaned_data:
            continue
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue
        # Defer saving file-type fields until after the other fields, so a
        # callable upload_to can use the values from other fields.
        if isinstance(f, models.FileField):
            file_field_list.append(f)
        else:
            f.save_form_data(instance, cleaned_data[f.name])

    for f in file_field_list:
        f.save_form_data(instance, cleaned_data[f.name])

    return instance


def fields_for_resource(
        resource, fields=None, exclude=None, widgets=None,
        formfield_callback=None, localized_fields=None,
        labels=None, help_texts=None, error_messages=None):
    field_list = []
    ignored = []
    opts = resource._meta
    # Avoid circular import
    from restorm.fields.base import Field as RestField
    sortable_virtual_fields = [f for f in opts.virtual_fields
                               if isinstance(f, RestField)]
    for f in sorted(chain(opts._fields.values(), sortable_virtual_fields)):
        if not getattr(f, 'editable', False):
            continue
        if fields is not None and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue

        kwargs = {}
        if widgets and f.name in widgets:
            kwargs['widget'] = widgets[f.name]
        if localized_fields == ALL_FIELDS or (localized_fields and f.name in localized_fields):  # NOQA
            kwargs['localize'] = True
        if labels and f.name in labels:
            kwargs['label'] = labels[f.name]
        if help_texts and f.name in help_texts:
            kwargs['help_text'] = help_texts[f.name]
        if error_messages and f.name in error_messages:
            kwargs['error_messages'] = error_messages[f.name]

        if formfield_callback is None:
            formfield = f.formfield(**kwargs)
        elif not callable(formfield_callback):
            raise TypeError(
                'formfield_callback must be a function or callable')
        else:
            formfield = formfield_callback(f, **kwargs)

        if formfield:
            field_list.append((f.name, formfield))
        else:
            ignored.append(f.name)
    field_dict = OrderedDict(field_list)
    if fields:
        field_dict = OrderedDict(
            [(f, field_dict.get(f)) for f in fields
                if ((not exclude) or (exclude and f not in exclude)) and (f not in ignored)]  # NOQA
        )
    return field_dict


def save_instance(form, instance, fields=None, fail_message='saved',
                  commit=True, exclude=None, construct=True):
    if construct:
        instance = construct_instance(form, instance, fields, exclude)
    opts = instance._meta
    if form.errors:
        raise ValueError("The %s could not be %s because the data didn't"
                         " validate." % (opts.object_name, fail_message))

    # Wrap up the saving of m2m data as a function.
    def save_m2m():
        cleaned_data = form.cleaned_data
        # Note that for historical reasons we want to include also
        # virtual_fields here. (GenericRelation was previously a fake
        # m2m field).
        for f in chain(opts.many_to_many, opts.virtual_fields):
            if not hasattr(f, 'save_form_data'):
                continue
            if fields and f.name not in fields:
                continue
            if exclude and f.name in exclude:
                continue
            if f.name in cleaned_data:
                f.save_form_data(instance, cleaned_data[f.name])
    if commit:
        # If we are committing, save the instance and the m2m data immediately.
        instance.save()
        save_m2m()
    else:
        # We're not committing. Add a method to the form to allow deferred
        # saving of m2m data.
        form.save_m2m = save_m2m
    return instance


def resource_to_dict(instance, fields=None, exclude=None):
        # avoid a circular import
    from restorm.fields.related import ToManyField
    opts = instance._meta
    data = {}
    model_fields = chain(
        opts.concrete_fields.values(), opts.virtual_fields, opts.many_to_many)
    for f in model_fields:
        if not getattr(f, 'editable', False):
            continue
        if fields and f.name not in fields:
            continue
        if exclude and f.name in exclude:
            continue
        if isinstance(f, ToManyField):
            # If the object doesn't have a primary key yet, just use an empty
            # list for its m2m fields. Calling f.value_from_object will raise
            # an exception.
            if instance.pk is None:
                data[f.name] = []
            else:
                # MultipleChoiceWidget needs a list of pks, not object instances.
                qs = f.value_from_object(instance)
                if (hasattr(qs, '_result_cache') and qs._result_cache is not None) or isinstance(qs, list):
                    try:
                        data[f.name] = [item.pk for item in qs]
                    except AttributeError:
                        data[f.name] = qs
                else:
                    data[f.name] = list(qs.values_list('pk', flat=True))
        else:
            data[f.name] = f.value_from_object(instance)
    return data


class RestFormOptions(object):
    def __init__(self, options=None):
        self.model = getattr(options, 'model', None)
        self.fields = getattr(options, 'fields', None)
        self.exclude = getattr(options, 'exclude', None)
        self.widgets = getattr(options, 'widgets', None)
        self.localized_fields = getattr(options, 'localized_fields', None)
        self.labels = getattr(options, 'labels', None)
        self.help_texts = getattr(options, 'help_texts', None)
        self.error_messages = getattr(options, 'error_messages', None)


class RestFormMetaclass(DeclarativeFieldsMetaclass):
    def __new__(mcs, name, bases, attrs):
        formfield_callback = attrs.pop('formfield_callback', None)

        new_class = super(RestFormMetaclass, mcs).__new__(
            mcs, name, bases, attrs)

        if bases == (BaseRestForm,):
            return new_class

        opts = new_class._meta = RestFormOptions(
            getattr(new_class, 'Meta', None))

        # We check if a string was passed to `fields` or `exclude`,
        # which is likely to be a mistake where the user typed ('foo') instead
        # of ('foo',)
        for opt in ['fields', 'exclude', 'localized_fields']:
            value = getattr(opts, opt)
            if isinstance(value, six.string_types) and value != ALL_FIELDS:
                msg = ("%(model)s.Meta.%(opt)s cannot be a string. "
                       "Did you mean to type: ('%(value)s',)?" % {
                           'model': new_class.__name__,
                           'opt': opt,
                           'value': value,
                       })
                raise TypeError(msg)

        if opts.model:
            # If a model is defined, extract form fields from it.
            if opts.fields is None and opts.exclude is None:
                raise ImproperlyConfigured(
                    "Creating a ModelForm without either the 'fields' attribute "
                    "or the 'exclude' attribute is prohibited; form %s "
                    "needs updating." % name
                )

            if opts.fields == ALL_FIELDS:
                # Sentinel for fields_for_model to indicate "get the list of
                # fields from the model"
                opts.fields = None

            fields = fields_for_resource(
                opts.model, opts.fields, opts.exclude,
                opts.widgets, formfield_callback,
                opts.localized_fields, opts.labels,
                opts.help_texts, opts.error_messages)

            # make sure opts.fields doesn't specify an invalid field
            none_model_fields = [k for k, v in six.iteritems(fields) if not v]
            missing_fields = (set(none_model_fields) -
                              set(new_class.declared_fields.keys()))
            if missing_fields:
                message = 'Unknown field(s) (%s) specified for %s'
                message = message % (', '.join(missing_fields),
                                     opts.model.__name__)
                raise FieldError(message)
            # Override default model fields with any custom declared ones
            # (plus, include all the other declared fields).
            fields.update(new_class.declared_fields)
        else:
            fields = new_class.declared_fields

        new_class.base_fields = fields

        return new_class


class BaseRestForm(BaseForm):
    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None):
        opts = self._meta
        if opts.model is None:
            raise ValueError('RestForm has no model class specified.')

        if instance is None:
            # if we didn't get an instance, instantiate a new one
            self.instance = opts.model()
            object_data = {}
        else:
            self.instance = instance
            object_data = resource_to_dict(instance, opts.fields, opts.exclude)
        # if initial was provided, it should override the values from instance
        if initial is not None:
            object_data.update(initial)
        # self._validate_unique will be set to True by BaseModelForm.clean().
        # It is False by default so overriding self.clean() and failing to call
        # super will stop validate_unique from being called.
        self._validate_unique = False
        super(BaseRestForm, self).__init__(
            data, files, auto_id, prefix, object_data,
            error_class, label_suffix, empty_permitted)
        # Apply ``limit_choices_to`` to each field.
        for field_name in self.fields:
            formfield = self.fields[field_name]
            if hasattr(formfield, 'queryset') and hasattr(
                    formfield, 'get_limit_choices_to'):
                limit_choices_to = formfield.get_limit_choices_to()
                if limit_choices_to is not None:
                    formfield.queryset = formfield.queryset.complex_filter(
                        limit_choices_to)

    def _get_validation_exclusions(self):
        """
        For backwards-compatibility, several types of fields need to be
        excluded from model validation. See the following tickets for
        details: #12507, #12521, #12553
        """
        exclude = []
        # Build up a list of fields that should be excluded from model field
        # validation and unique checks.
        for f in self.instance._meta._fields.values():
            field = f.name
            # Exclude fields that aren't on the form. The developer may be
            # adding these values to the model after form validation.
            if field not in self.fields:
                exclude.append(f.name)

            # Don't perform model validation on fields that were defined
            # manually on the form and excluded via the ModelForm's Meta
            # class. See #12901.
            elif self._meta.fields and field not in self._meta.fields:
                exclude.append(f.name)
            elif self._meta.exclude and field in self._meta.exclude:
                exclude.append(f.name)

            # Exclude fields that failed form validation. There's no need for
            # the model fields to validate them as well.
            elif field in self._errors.keys():
                exclude.append(f.name)

            # Exclude empty fields that are not required by the form, if the
            # underlying model field is required. This keeps the model field
            # from raising a required error. Note: don't exclude the field from
            # validation if the model field allows blanks. If it does, the blank
            # value may be included in a unique check, so cannot be excluded
            # from validation.
            else:
                form_field = self.fields[field]
                field_value = self.cleaned_data.get(field, None)
                if not f.blank and not form_field.required and \
                        field_value in form_field.empty_values:
                    exclude.append(f.name)
        return exclude

    def clean(self):
        self._validate_unique = True
        return self.cleaned_data

    def _update_errors(self, errors):
        # Override any validation error messages defined at the model level
        # with those defined at the form level.
        opts = self._meta
        for field, messages in errors.error_dict.items():
            if (field == NON_FIELD_ERRORS and opts.error_messages and
                    NON_FIELD_ERRORS in opts.error_messages):
                error_messages = opts.error_messages[NON_FIELD_ERRORS]
            elif field in self.fields:
                error_messages = self.fields[field].error_messages
            else:
                continue

            for message in messages:
                if (isinstance(message, ValidationError) and
                        message.code in error_messages):
                    message.message = error_messages[message.code]

        self.add_error(None, errors)

    def _post_clean(self):
        opts = self._meta

        exclude = self._get_validation_exclusions()

        try:
            self.instance = construct_instance(
                self, self.instance, opts.fields, exclude)
        except ValidationError as e:
            self._update_errors(e)

        # Foreign Keys being used to represent inline relationships
        # are excluded from basic field value validation. This is for two
        # reasons: firstly, the value may not be supplied (#12507; the
        # case of providing new values to the admin); secondly the
        # object being referred to may not yet fully exist (#12749).
        # However, these fields *must* be included in uniqueness checks,
        # so this can't be part of _get_validation_exclusions().
        for name, field in self.fields.items():
            if isinstance(field, InlineForeignKeyField):
                exclude.append(name)

        try:
            self.instance.full_clean(exclude=exclude, validate_unique=False)
        except ValidationError as e:
            self._update_errors(e)

        # Validate uniqueness if needed.
        if self._validate_unique:
            self.validate_unique()

    def validate_unique(self):
        """
        Calls the instance's validate_unique() method and updates the form's
        validation errors if any were raised.
        """
        exclude = self._get_validation_exclusions()
        try:
            self.instance.validate_unique(exclude=exclude)
        except ValidationError as e:
            self._update_errors(e)

    def save(self, commit=True):
        """
        Saves this ``form``'s cleaned_data into model instance
        ``self.instance``.
        If commit=True, then the changes to ``instance`` will be saved to the
        database. Returns ``instance``.
        """
        if self.instance.pk is None:
            fail_message = 'created'
        else:
            fail_message = 'changed'
        return save_instance(self, self.instance, self._meta.fields,
                             fail_message, commit, self._meta.exclude,
                             construct=False)

    save.alters_data = True


class RestForm(six.with_metaclass(RestFormMetaclass, BaseRestForm)):
    pass


def restform_factory(
        resource, form=RestForm, fields=None, exclude=None,
        formfield_callback=None, widgets=None, localized_fields=None,
        labels=None, help_texts=None, error_messages=None):
    """
    Returns a RestForm containing form fields for the given resource.
    ``fields`` is an optional list of field names. If provided, only the named
    fields will be included in the returned fields. If omitted or '__all__',
    all fields will be used.
    ``exclude`` is an optional list of field names. If provided, the named
    fields will be excluded from the returned fields, even if they are listed
    in the ``fields`` argument.
    ``widgets`` is a dictionary of resource field names mapped to a widget.
    ``localized_fields`` is a list of names of fields which should be localized.
    ``formfield_callback`` is a callable that takes a resource field and returns
    a form field.
    ``labels`` is a dictionary of resource field names mapped to a label.
    ``help_texts`` is a dictionary of resource field names mapped to a help text.
    ``error_messages`` is a dictionary of resource field names mapped to a
    dictionary of error messages.
    """
    # Create the inner Meta class. FIXME: ideally, we should be able to
    # construct a RestForm without creating and passing in a temporary
    # inner class.

    # Build up a list of attributes that the Meta object will have.
    attrs = {'model': resource}
    if fields is not None:
        attrs['fields'] = fields
    if exclude is not None:
        attrs['exclude'] = exclude
    if widgets is not None:
        attrs['widgets'] = widgets
    if localized_fields is not None:
        attrs['localized_fields'] = localized_fields
    if labels is not None:
        attrs['labels'] = labels
    if help_texts is not None:
        attrs['help_texts'] = help_texts
    if error_messages is not None:
        attrs['error_messages'] = error_messages

    # If parent form class already has an inner Meta, the Meta we're
    # creating needs to inherit from the parent's inner meta.
    parent = (object,)
    if hasattr(form, 'Meta'):
        parent = (form.Meta, object)
    Meta = type(str('Meta'), parent, attrs)

    # Give this new form class a reasonable name.
    class_name = resource.__name__ + str('Form')

    # Class attributes for the new form class.
    form_class_attrs = {
        'Meta': Meta,
        'formfield_callback': formfield_callback
    }

    if (getattr(Meta, 'fields', None) is None and
            getattr(Meta, 'exclude', None) is None):
        raise ImproperlyConfigured(
            "Calling modelform_factory without defining 'fields' or "
            "'exclude' explicitly is prohibited."
        )

    # Instantiate type(form) in order to use the same metaclass as form.
    return type(form)(class_name, (form,), form_class_attrs)


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
        assert False, value
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
