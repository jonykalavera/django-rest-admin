from django.contrib.admin.options import (
    ModelAdmin, TO_FIELD_VAR, IS_POPUP_VAR,
    csrf_protect_m, DisallowedModelAdminToField,
    PermissionDenied, unquote, Http404, force_text, escape,
    _, InlineModelAdmin, widgets, get_ul_class,
    FORMFIELD_FOR_DBFIELD_DEFAULTS, transaction, reverse, all_valid, helpers
)
from django.forms.widgets import SelectMultiple, CheckboxSelectMultiple
from restorm import fields as rest_fields
from restorm.fields.related import ToOneField, ToManyField
from restorm.exceptions import RestValidationException
from rest_admin.forms import RestForm, restform_factory
from rest_admin import widgets as rest_admin_widgets
from rest_admin.utils import patch


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
    # rest_fields.ImageField: {'widget': widgets.AdminFileWidget},
    # rest_fields.FileField: {'widget': widgets.AdminFileWidget},
    # rest_fields.EmailField: {'widget': widgets.AdminEmailInputWidget},
})


class RestAdmin(ModelAdmin):
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

    def get_fields(self, request, obj=None):
        """
        Hook for specifying fields.
        """
        # FIXME
        return [
            k for k, v in self.opts._fields.items() if v.editable]

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
        deleted_objects, model_count, perms_needed, protected = [obj], {self.model.__name__:1}, [], []

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

    def formfield_for_dbfield(self, db_field, **kwargs):
        with patch('django.db.models.ForeignKey', ToOneField):
            with patch('django.db.models.ManyToManyField', ToManyField):
                return super(RestAdmin, self).formfield_for_dbfield(
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
        # if not db_field.rel.through._meta.auto_created:
        #     return None
        db = kwargs.get('using')

        if db_field.name in self.raw_id_fields:
            kwargs['widget'] = rest_admin_widgets.ToManyRawIdWidget(
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
        if isinstance(form_field.widget, SelectMultiple) and not isinstance(form_field.widget, CheckboxSelectMultiple):
            msg = _('Hold down "Control", or "Command" on a Mac, to select more than one.')
            help_text = form_field.help_text
            form_field.help_text = string_concat(help_text, ' ', msg) if help_text else msg
        return form_field


class InlineRestAdmin(InlineModelAdmin):
    def get_formset(self, request, obj=None, **kwargs):
        assert False, obj
        super(InlineRestAdmin, self).get_formset(request, obj, **kwargs)


class StackedRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/stacked.html'


class TabularRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/tabular.html'
