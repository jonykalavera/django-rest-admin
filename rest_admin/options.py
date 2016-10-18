# -*- coding: utf-8 -*-
from django.contrib.admin.options import (
    ModelAdmin, TO_FIELD_VAR, IS_POPUP_VAR,
    csrf_protect_m, DisallowedModelAdminToField,
    PermissionDenied, unquote, Http404, force_text, escape, _,
    InlineModelAdmin, widgets, get_ul_class,
    FORMFIELD_FOR_DBFIELD_DEFAULTS, transaction, reverse, all_valid, helpers,
    flatten_fieldsets, partial, DELETION_FIELD_NAME, string_concat, modelform_defines_fields,
    forms
)

from django import VERSION
from django.contrib.admin.templatetags.admin_static import static
from django.conf import settings
from django.forms.widgets import SelectMultiple, CheckboxSelectMultiple
from restorm import fields as rest_fields
from restorm.fields.related import ToOneField, ToManyField
from restorm.forms import (
    RestForm, restform_factory, BaseInlineRestFormSet, inlinerestformset_factory
)
from restorm.exceptions import RestValidationException
from restorm.utils import patch

from rest_admin import widgets as rest_admin_widgets


# Defaults for restorm fields. ModelAdmin subclasses can change this
# by adding to ModelAdmin.formfield_overrides.
# Leaving commented lines for currently unsupported fields
FORMFIELD_FOR_DBFIELD_DEFAULTS.update({
    rest_fields.DateTimeField: {
        # 'form_class': forms.SplitDateTimeField,
        'widget': widgets.AdminSplitDateTime
    },
    rest_fields.DateField: {'widget': widgets.AdminDateWidget},
    # rest_fields.TimeField: {'widget': widgets.AdminTimeWidget},
    rest_fields.TextField: {'widget': widgets.AdminTextareaWidget},
    rest_fields.URLField: {'widget': widgets.AdminURLFieldWidget},
    rest_fields.IntegerField: {'widget': widgets.AdminIntegerFieldWidget},
    # rest_fields.BigIntegerField: {'widget': widgets.AdminBigIntegerFieldWidget},
    rest_fields.CharField: {'widget': widgets.AdminTextInputWidget},
    rest_fields.JSONField: {'widget': widgets.AdminTextareaWidget},
    # rest_fields.ImageField: {'widget': widgets.AdminFileWidget},
    # rest_fields.FileField: {'widget': widgets.AdminFileWidget},
    # rest_fields.EmailField: {'widget': widgets.AdminEmailInputWidget},
})


class RestAdminBase(object):
    def formfield_for_dbfield(self, db_field, **kwargs):
        with patch('django.db.models.ForeignKey', ToOneField):
            with patch('django.db.models.ManyToManyField', ToManyField):
                return super(RestAdminBase, self).formfield_for_dbfield(
                    db_field, **kwargs)

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Get a form Field for a ForeignKey.
        """
        # with patch(
        #         'django.contrib.admin.widgets.ForeignKeyRawIdWidget',
        #         rest_admin_widgets.ToManyFieldRawIdWidget):
        #     return super(RestAdmin, self).formfield_for_foreignkey(
        #         db_field, request, **kwargs)

        db = kwargs.get('using')
        if db_field.name in self.raw_id_fields:
            kwargs['widget'] = rest_admin_widgets.ToOneFieldRawIdWidget(
                db_field.rel, self.admin_site, using=db)
        elif db_field.name in self.radio_fields:
            kwargs['widget'] = widgets.AdminRadioSelect(attrs={
                'class': get_ul_class(self.radio_fields[db_field.name]),
            })
            kwargs['empty_label'] = _('None') if db_field.blank else None

        if 'queryset' not in kwargs:
            queryset = self.get_field_queryset(db, db_field, request)
            if queryset is not None:
                kwargs['queryset'] = queryset

        return db_field.formfield(**kwargs)

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """
        Get a form Field for a ManyToManyField.
        """
        # If it uses an intermediary model that isn't auto created, don't show
        # a field in admin.
        if hasattr(db_field.rel, 'through') and db_field.rel.through:
            return None
        db = kwargs.get('using')

        if db_field.name in self.raw_id_fields:
            kwargs['widget'] = rest_admin_widgets.ToManyFieldRawIdWidget(
                db_field.rel, self.admin_site, using=db)
            kwargs['help_text'] = ''
        elif db_field.name in (list(self.filter_vertical) + list(self.filter_horizontal)):
            kwargs['widget'] = widgets.FilteredSelectMultiple(
                db_field.verbose_name,
                db_field.name in self.filter_vertical
            )

        if 'queryset' not in kwargs:
            queryset = self.get_field_queryset(db, db_field, request)
            if queryset is not None:
                kwargs['queryset'] = queryset

        form_field = db_field.formfield(**kwargs)
        if isinstance(form_field.widget, SelectMultiple) and \
                not isinstance(form_field.widget, CheckboxSelectMultiple):
            msg = _('Hold down "Control", or "Command" on a Mac, to select more than one.')
            help_text = form_field.help_text
            form_field.help_text = string_concat(help_text, ' ', msg) if help_text else msg
        return form_field


class RestAdmin(RestAdminBase, ModelAdmin):
    form = RestForm

    def get_actions(self, request):
        return None

    def get_form(self, request, obj=None, **kwargs):
        with patch('django.forms.models.modelform_factory', restform_factory):
            return super(RestAdmin, self).get_form(request, obj, **kwargs)

    def get_changelist(self, request, **kwargs):
        """
        Returns the ChangeList class for use on the changelist page.
        """
        from rest_admin.views import RestChangeList
        return RestChangeList

    def render_change_form(self, *args, **kwargs):
        class ContentType:
            pk = None

        content_type = ContentType()

        def get_content_type_for_model(model):
            return content_type

        with patch(
                'django.contrib.admin.options.get_content_type_for_model',
                get_content_type_for_model):
            return super(RestAdmin, self).render_change_form(*args, **kwargs)

    def log_addition(self, *args, **kwargs):
        pass

    def log_change(self, *args, **kwargs):
        pass

    @csrf_protect_m
    @transaction.atomic
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        model = self.model
        opts = model._meta
        add = object_id is None

        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id), to_field)

            if not self.has_change_permission(request, obj):
                raise PermissionDenied

            if obj is None:
                raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {
                    'name': force_text(opts.verbose_name), 'key': escape(object_id)})

            if request.method == 'POST' and "_saveasnew" in request.POST:
                return self.add_view(request, form_url=reverse('admin:%s_%s_add' % (
                    opts.app_label, opts.model_name),
                    current_app=self.admin_site.name))

        ModelForm = self.get_form(request, obj)

        if request.method == 'POST':
            form = ModelForm(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                form_validated = True
                new_object = self.save_form(request, form, change=not add)
            else:
                form_validated = False
                new_object = form.instance
            if type(new_object.data) != dict:
                new_object.data = new_object.data.data
            formsets, inline_instances = self._create_formsets(request, new_object, change=not add)
            if all_valid(formsets) and form_validated:
                try:
                    self.save_model(request, new_object, form, not add)
                    self.save_related(request, form, formsets, not add)
                    if add:
                        self.log_addition(request, new_object)
                        return self.response_add(request, new_object)
                    else:
                        change_message = self.construct_change_message(request, form, formsets)
                        self.log_change(request, new_object, change_message)
                        return self.response_change(request, new_object)
                except RestValidationException as err:
                    for key, errors in err.response.content.items():
                        if key == 'non_field_errors':
                            field = None
                        else:
                            field = key
                        for error in errors:
                            form.add_error(field, error)
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(request, self.model(), change=False)
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(request, obj, change=True)

        adminForm = helpers.AdminForm(
            form,
            list(self.get_fieldsets(request, obj)),
            self.get_prepopulated_fields(request, obj),
            self.get_readonly_fields(request, obj),
            model_admin=self)
        media = self.media + adminForm.media

        inline_formsets = self.get_inline_formsets(request, formsets, inline_instances, obj)
        for inline_formset in inline_formsets:
            media = media + inline_formset.media

        context = dict(self.admin_site.each_context(request),
            title=(_('Add %s') if add else _('Change %s')) % force_text(opts.verbose_name),
            adminform=adminForm,
            object_id=object_id,
            original=obj,
            is_popup=(IS_POPUP_VAR in request.POST or
                      IS_POPUP_VAR in request.GET),
            to_field=to_field,
            media=media,
            inline_admin_formsets=inline_formsets,
            errors=helpers.AdminErrorList(form, formsets),
            preserved_filters=self.get_preserved_filters(request),
        )

        context.update(extra_context or {})

        return self.render_change_form(request, context, add=add, change=not add, obj=obj, form_url=form_url)

    def _create_formsets(self, request, obj, change):
        "Helper function to generate formsets for add/change_view."
        formsets = []
        inline_instances = []
        prefixes = {}
        get_formsets_args = [request]
        if change:
            get_formsets_args.append(obj)
        for FormSet, inline in self.get_formsets_with_inlines(*get_formsets_args):
            prefix = FormSet.get_default_prefix()
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
            if prefixes[prefix] != 1 or not prefix:
                prefix = "%s-%s" % (prefix, prefixes[prefix])
            formset_params = {
                'instance': obj,
                'prefix': prefix,
                'queryset': inline.get_queryset(request),
            }
            if request.method == 'POST':
                formset_params.update({
                    'data': request.POST,
                    'files': request.FILES,
                    'save_as_new': '_saveasnew' in request.POST
                })

            formset = FormSet(**formset_params)
            formsets.append(formset)
            inline_instances.append(inline)
        return formsets, inline_instances

    def log_deletion(self, *args, **kwargs):
        pass

    @csrf_protect_m
    def delete_view(self, request, object_id, extra_context=None):
        # def get_deleted_objects(*args, **kwargs):
        #     result = (args[0], {self.model.__name__: 1}, [], [])
        #     return result
        #
        # with patch(
        #         'django.contrib.admin.utils.get_deleted_objects',
        #         new=get_deleted_objects):
        #     return super(RestAdmin, self).delete_view(
        #         request, object_id, extra_context)
        "The 'delete' admin view for this model."
        opts = self.model._meta
        app_label = opts.app_label

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        obj = self.get_object(request, unquote(object_id), to_field)

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(
                _('%(name)s object with primary key %(key)r does not exist.') %
                {'name': force_text(opts.verbose_name), 'key': escape(object_id)}
            )

        # using = router.db_for_write(self.model)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.
        deleted_objects, model_count, perms_needed, protected = [obj], {self.model.__name__: 1}, [], []

        if request.POST:  # The user has already confirmed the deletion.
            if perms_needed:
                raise PermissionDenied
            obj_display = force_text(obj)
            attr = str(to_field) if to_field else opts.pk.attname
            obj_id = obj.serializable_value(attr)
            # self.log_deletion(request, obj, obj_display)
            self.delete_model(request, obj)

            return self.response_delete(request, obj_display, obj_id)

        object_name = force_text(opts.verbose_name)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Are you sure?")

        context = dict(
            self.admin_site.each_context(request),
            title=title,
            object_name=object_name,
            object=obj,
            deleted_objects=deleted_objects,
            model_count=dict(model_count).items(),
            perms_lacking=perms_needed,
            protected=protected,
            opts=opts,
            app_label=app_label,
            preserved_filters=self.get_preserved_filters(request),
            is_popup=(IS_POPUP_VAR in request.POST or
                      IS_POPUP_VAR in request.GET),
            to_field=to_field,
        )
        context.update(extra_context or {})

        return self.render_delete_form(request, context)


class InlineRestAdmin(RestAdminBase, InlineModelAdmin):
    form = RestForm
    formset = BaseInlineRestFormSet

    def get_formset(self, request, obj=None, **kwargs):
        """Returns a BaseInlineFormSet class for use in admin add/change views."""
        if 'fields' in kwargs:
            fields = kwargs.pop('fields')
        else:
            fields = flatten_fieldsets(self.get_fieldsets(request, obj))
        if self.exclude is None:
            exclude = []
        else:
            exclude = list(self.exclude)
        exclude.extend(self.get_readonly_fields(request, obj))
        if self.exclude is None and hasattr(self.form, '_meta') and self.form._meta.exclude:
            # Take the custom ModelForm's Meta.exclude into account only if the
            # InlineModelAdmin doesn't define its own.
            exclude.extend(self.form._meta.exclude)
        # If exclude is an empty list we use None, since that's the actual
        # default.
        exclude = exclude or None
        can_delete = self.can_delete and self.has_delete_permission(request, obj)
        defaults = {
            "form": self.form,
            "formset": self.formset,
            "fk_name": self.fk_name,
            "fields": fields,
            "exclude": exclude,
            "formfield_callback": partial(self.formfield_for_dbfield, request=request),
            "extra": self.get_extra(request, obj, **kwargs),
            "min_num": self.get_min_num(request, obj, **kwargs),
            "max_num": self.get_max_num(request, obj, **kwargs),
            "can_delete": can_delete,
        }

        defaults.update(kwargs)
        base_model_form = defaults['form']

        class DeleteProtectedModelForm(base_model_form):
            def hand_clean_DELETE(self):
                """
                We don't validate the 'DELETE' field itself because on
                templates it's not rendered using the field information, but
                just using a generic "deletion_field" of the InlineModelAdmin.
                """
                if self.cleaned_data.get(DELETION_FIELD_NAME, False):
                    # using = router.db_for_write(self._meta.model)
                    # collector = NestedObjects(using=using)
                    if self.instance.pk is None:
                        return
                    # collector.collect([self.instance])
                    # if collector.protected:
                    #     objs = []
                    #     for p in collector.protected:
                    #         objs.append(
                    #             # Translators: Model verbose name and instance representation,
                    #             # suitable to be an item in a list.
                    #             _('%(class_name)s %(instance)s') % {
                    #                 'class_name': p._meta.verbose_name,
                    #                 'instance': p}
                    #         )
                    #     params = {'class_name': self._meta.model._meta.verbose_name,
                    #               'instance': self.instance,
                    #               'related_objects': get_text_list(objs, _('and'))}
                    #     msg = _("Deleting %(class_name)s %(instance)s would require "
                    #             "deleting the following protected related objects: "
                    #             "%(related_objects)s")
                    #     raise ValidationError(msg, code='deleting_protected', params=params)

            def is_valid(self):
                result = super(DeleteProtectedModelForm, self).is_valid()
                self.hand_clean_DELETE()
                return result

        defaults['form'] = DeleteProtectedModelForm

        if defaults['fields'] is None and not modelform_defines_fields(defaults['form']):
            defaults['fields'] = forms.ALL_FIELDS
        return inlinerestformset_factory(self.parent_model, self.model, **defaults)


class NestedRestAdmin(RestAdmin):

    class Media:
        css = {
            "all": ('admin/css/forms-nested.css',)
        }
        js = ('admin/js/inlines-nested.js',)

    def get_inline_instances(self, request, obj=None):
        inline_instances = []
        for inline_class in self.inlines:
            inline = inline_class(self.model, self.admin_site)
            if request:
                if not (inline.has_add_permission(request) or
                        inline.has_change_permission(request, obj) or
                        inline.has_delete_permission(request, obj)):
                    continue
                if not inline.has_add_permission(request):
                    inline.max_num = 0
            inline_instances.append(inline)

        return inline_instances

    def save_formset(self, request, form, formset, change):
        """
        Given an inline formset save it to the database.
        """
        instances = formset.save()

        for form in formset.forms:
            if hasattr(form, 'nested_formsets') and form not in formset.deleted_forms:
                for nested_formset in form.nested_formsets:
                    self.save_formset(request, form, nested_formset, change)

    def save_related(self, request, form, formsets, change):
        """
        Given the ``HttpRequest``, the parent ``ModelForm`` instance, the
        list of inline formsets and a boolean value based on whether the
        parent is being added or changed, save the related objects to the
        database. Note that at this point save_form() and save_model() have
        already been called.
        """
        form.save_m2m()
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)

    def add_nested_inline_formsets(self, request, inline, formset, depth=0):
        if depth > 5:
            raise Exception("Maximum nesting depth reached (5)")
        for form in formset.forms:
            nested_formsets = []
            for nested_inline in inline.get_inline_instances(request):
                InlineFormSet = nested_inline.get_formset(request, form.instance)
                prefix = "%s-%s" % (form.prefix, InlineFormSet.get_default_prefix())

                if request.method == 'POST' and any(s.startswith(prefix) for s in request.POST.keys()):
                    nested_formset = InlineFormSet(request.POST, request.FILES,
                        instance=form.instance,
                        prefix=prefix, queryset=nested_inline.get_queryset(request))
                else:
                    nested_formset = InlineFormSet(instance=form.instance,
                        prefix=prefix, queryset=nested_inline.get_queryset(request))
                nested_formsets.append(nested_formset)
                if nested_inline.inlines:
                    self.add_nested_inline_formsets(request, nested_inline, nested_formset, depth=depth+1)
            form.nested_formsets = nested_formsets

    def wrap_nested_inline_formsets(self, request, inline, formset):
        media = None
        def get_media(extra_media):
            if media:
                return media + extra_media
            else:
                return extra_media

        for form in formset.forms:
            wrapped_nested_formsets = []
            for nested_inline, nested_formset in zip(inline.get_inline_instances(request), form.nested_formsets):
                if form.instance.pk:
                    instance = form.instance
                else:
                    instance = None
                fieldsets = list(nested_inline.get_fieldsets(request))
                readonly = list(nested_inline.get_readonly_fields(request))
                prepopulated = dict(nested_inline.get_prepopulated_fields(request))
                wrapped_nested_formset = helpers.InlineAdminFormSet(nested_inline, nested_formset,
                    fieldsets, prepopulated, readonly, model_admin=self)
                wrapped_nested_formsets.append(wrapped_nested_formset)
                media = get_media(wrapped_nested_formset.media)
                if nested_inline.inlines:
                    media = get_media(self.wrap_nested_inline_formsets(request, nested_inline, nested_formset))
            form.nested_formsets = wrapped_nested_formsets
        return media

    def formset_has_nested_data(self, formsets):
        for formset in formsets:
            if not formset.is_bound:
                pass
            for form in formset:
                if hasattr(form, 'cleaned_data') and form.cleaned_data:
                    return True
                elif hasattr(form, 'nested_formsets'):
                    if self.formset_has_nested_data(form.nested_formsets):
                        return True


    def all_valid_with_nesting(self, formsets):
        "Recursively validate all nested formsets"
        if not all_valid(formsets):
            return False

        for formset in formsets:
            if not formset.is_bound:
                pass
            for form in formset:
                if hasattr(form, 'nested_formsets'):
                    if not self.all_valid_with_nesting(form.nested_formsets):
                        return False

                    #TODO - find out why this breaks when extra = 1 and just adding new item with no sub items
                    if (not hasattr(form, 'cleaned_data') or not form.cleaned_data) and self.formset_has_nested_data(form.nested_formsets):
                        form._errors["__all__"] = form.error_class([u"Parent object must be created when creating nested inlines."])
                        return False
        return True

    @csrf_protect_m
    @transaction.atomic
    def add_view(self, request, form_url='', extra_context=None):
        "The 'add' admin view for this model."
        model = self.model
        opts = model._meta

        if not self.has_add_permission(request):
            raise PermissionDenied

        ModelForm = self.get_form(request)
        formsets = []
        inline_instances = self.get_inline_instances(request, None)
        if request.method == 'POST':
            form = ModelForm(request.POST, request.FILES)
            if form.is_valid():
                new_object = self.save_form(request, form, change=False)
                form_validated = True
            else:
                form_validated = False
                new_object = self.model()
            prefixes = {}
            for FormSet, inline in self.get_formsets_with_inlines(request):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(data=request.POST, files=request.FILES,
                    instance=new_object,
                    save_as_new="_saveasnew" in request.POST,
                    prefix=prefix, queryset=inline.get_queryset(request))
                formsets.append(formset)
                if inline.inlines:
                    self.add_nested_inline_formsets(request, inline, formset)
            if self.all_valid_with_nesting(formsets) and form_validated:
                self.save_model(request, new_object, form, False)
                self.save_related(request, form, formsets, False)
                args = ()
                # Provide `add_message` argument to ModelAdmin.log_addition for
                # Django 1.9 and up.
                if VERSION[:2] >= (1, 9):
                    add_message = self.construct_change_message(
                        request, form, formsets, add=True
                    )
                    args = (request, new_object, add_message)
                else:
                    args = (request, new_object)
                self.log_addition(*args)
                return self.response_add(request, new_object)
        else:
            # Prepare the dict of initial data from the request.
            # We have to special-case M2Ms as a list of comma-separated PKs.
            initial = dict(request.GET.items())
            for k in initial:
                try:
                    f = opts.get_field(k)
                except models.FieldDoesNotExist:
                    continue
                if isinstance(f, models.ManyToManyField):
                    initial[k] = initial[k].split(",")
            form = ModelForm(initial=initial)
            prefixes = {}
            for FormSet, inline in self.get_formsets_with_inlines(request):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(instance=self.model(), prefix=prefix,
                    queryset=inline.get_queryset(request))
                formsets.append(formset)
                if hasattr(inline, 'inlines') and inline.inlines:
                    self.add_nested_inline_formsets(request, inline, formset)

        adminForm = helpers.AdminForm(form, list(self.get_fieldsets(request)),
            self.get_prepopulated_fields(request),
            self.get_readonly_fields(request),
            model_admin=self)
        media = self.media + adminForm.media

        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request))
            readonly = list(inline.get_readonly_fields(request))
            prepopulated = dict(inline.get_prepopulated_fields(request))
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            inline_admin_formsets.append(inline_admin_formset)
            media = media + inline_admin_formset.media
            if hasattr(inline, 'inlines') and inline.inlines:
                media += self.wrap_nested_inline_formsets(request, inline, formset)

        context = {
            'title': _('Add %s') % force_text(opts.verbose_name),
            'adminform': adminForm,
            'is_popup': "_popup" in request.GET,
            'show_delete': False,
            'media': media,
            'inline_admin_formsets': inline_admin_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'app_label': opts.app_label,
            }
        context.update(extra_context or {})
        return self.render_change_form(request, context, form_url=form_url, add=True)

    @csrf_protect_m
    @transaction.atomic
    def change_view(self, request, object_id, form_url='', extra_context=None):
        "The 'change' admin view for this model."
        model = self.model
        opts = model._meta

        obj = self.get_object(request, unquote(object_id))

        if not self.has_change_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {'name': force_text(opts.verbose_name), 'key': escape(object_id)})

        if request.method == 'POST' and "_saveasnew" in request.POST:
            return self.add_view(request, form_url=reverse('admin:%s_%s_add' %
                                                           (opts.app_label, opts.module_name),
                current_app=self.admin_site.name))

        ModelForm = self.get_form(request, obj)
        formsets = []
        inline_instances = self.get_inline_instances(request, obj)
        if request.method == 'POST':
            form = ModelForm(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                form_validated = True
                new_object = self.save_form(request, form, change=True)
            else:
                form_validated = False
                new_object = obj
            prefixes = {}
            for FormSet, inline in self.get_formsets_with_inlines(request, new_object):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(request.POST, request.FILES,
                    instance=new_object, prefix=prefix,
                    queryset=inline.get_queryset(request))
                formsets.append(formset)
                if hasattr(inline, 'inlines') and inline.inlines:
                    self.add_nested_inline_formsets(request, inline, formset)

            if self.all_valid_with_nesting(formsets) and form_validated:
                self.save_model(request, new_object, form, True)
                self.save_related(request, form, formsets, True)
                change_message = self.construct_change_message(request, form, formsets)
                self.log_change(request, new_object, change_message)
                return self.response_change(request, new_object)

        else:
            form = ModelForm(instance=obj)
            prefixes = {}
            for FormSet, inline in self.get_formsets_with_inlines(request, obj):
                prefix = FormSet.get_default_prefix()
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
                if prefixes[prefix] != 1 or not prefix:
                    prefix = "%s-%s" % (prefix, prefixes[prefix])
                formset = FormSet(instance=obj, prefix=prefix,
                    queryset=inline.get_queryset(request))
                formsets.append(formset)
                if hasattr(inline, 'inlines') and inline.inlines:
                    self.add_nested_inline_formsets(request, inline, formset)

        adminForm = helpers.AdminForm(form, self.get_fieldsets(request, obj),
            self.get_prepopulated_fields(request, obj),
            self.get_readonly_fields(request, obj),
            model_admin=self)
        media = self.media + adminForm.media

        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            readonly = list(inline.get_readonly_fields(request, obj))
            prepopulated = dict(inline.get_prepopulated_fields(request, obj))
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            inline_admin_formsets.append(inline_admin_formset)
            media = media + inline_admin_formset.media
            if hasattr(inline, 'inlines') and inline.inlines:
                media += self.wrap_nested_inline_formsets(request, inline, formset)

        context = {
            'title': _('Change %s') % force_text(opts.verbose_name),
            'adminform': adminForm,
            'object_id': object_id,
            'original': obj,
            'is_popup': "_popup" in request.GET,
            'media': media,
            'inline_admin_formsets': inline_admin_formsets,
            'errors': helpers.AdminErrorList(form, formsets),
            'app_label': opts.app_label,
            }
        context.update(extra_context or {})
        return self.render_change_form(request, context, change=True, obj=obj, form_url=form_url)



class NestedInline(InlineRestAdmin):
    inlines = []
    new_objects = []

    @property
    def media(self):

        extra = '' if settings.DEBUG else '.min'
        js = ['jquery%s.js' % extra, 'jquery.init.js', 'inlines-nested%s.js' % extra]
        if self.prepopulated_fields:
            js.extend(['urlify.js', 'prepopulate%s.js' % extra])
        if self.filter_vertical or self.filter_horizontal:
            js.extend(['SelectBox.js', 'SelectFilter2.js'])
        return forms.Media(js=[static('admin/js/%s' % url) for url in js])

    def get_inline_instances(self, request, obj=None):
        inline_instances = []
        for inline_class in self.inlines:
            inline = inline_class(self.model, self.admin_site)
            if request:
                if not (inline.has_add_permission(request) or
                        inline.has_change_permission(request, obj) or
                        inline.has_delete_permission(request, obj)):
                    continue
                if not inline.has_add_permission(request):
                    inline.max_num = 0
            inline_instances.append(inline)
        return inline_instances

    def get_formsets_with_inlines(self, request, obj=None):
        for inline in self.get_inline_instances(request):
            yield inline.get_formset(request, obj), inline


class NestedStackedInline(NestedInline):
    template = 'admin/edit_inline/stacked-nested.html'


class NestedTabularInline(NestedInline):
    template = 'admin/edit_inline/tabular-nested.html'



class StackedRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/stacked.html'


class TabularRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/tabular.html'
