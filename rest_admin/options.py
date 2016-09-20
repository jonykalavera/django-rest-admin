from django.contrib.admin.options import (
    ModelAdmin, add_preserved_filters, TO_FIELD_VAR, IS_POPUP_VAR,
    TemplateResponse, csrf_protect_m, DisallowedModelAdminToField,
    PermissionDenied, unquote, Http404, force_text, reverse, escape, escapejs,
    all_valid, helpers, _, messages, HttpResponseRedirect,
    SimpleTemplateResponse, quote, InlineModelAdmin
)
from restorm.fields.related import ToManyField
from restorm.exceptions import RestException
from rest_admin.forms import RestForm


class RestAdmin(ModelAdmin):
    # change_list_template = 'rest_admin/change_list.html'
    # change_form_template = 'rest_admin/change_form.html'

    def get_actions(self, request):
        return None

    def get_form(self, request, obj=None, **kwargs):
        form = RestForm
        setattr(form, 'resource', self.model)
        setattr(form, 'admin', self)
        return form

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
        return [
            k for k, v in self.opts._fields.items() if v.editable]

    @csrf_protect_m
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
            formsets, inline_instances = self._create_formsets(request, new_object, change=not add)
            if all_valid(formsets) and form_validated:
                self.save_model(request, new_object, form, not add)
                self.save_related(request, form, formsets, not add)
                if add:
                    self.log_addition(request, new_object)
                    return self.response_add(request, new_object)
                else:
                    change_message = self.construct_change_message(request, form, formsets)
                    self.log_change(request, new_object, change_message)
                    return self.response_change(request, new_object)
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(request, self.model(), change=False)
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(request, obj, change=True)

        fieldsets = self.get_fieldsets(request, obj)
        adminForm = helpers.AdminForm(
            form,
            list(fieldsets),
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

    def render_change_form(self, request, context, add=False, change=False, form_url='', obj=None):
        opts = self.model._meta
        app_label = opts.app_label
        preserved_filters = self.get_preserved_filters(request)
        form_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, form_url)
        view_on_site_url = self.get_view_on_site_url(obj)
        # assert False, context
        context.update({
            'add': add,
            'change': change,
            'has_add_permission': self.has_add_permission(request),
            'has_change_permission': self.has_change_permission(request, obj),
            'has_delete_permission': self.has_delete_permission(request, obj),
            'has_file_field': True,  # FIXME - this should check if form or formsets have a FileField,
            'has_absolute_url': view_on_site_url is not None,
            'absolute_url': view_on_site_url,
            'form_url': form_url,
            'opts': opts,
            # 'content_type_id': get_content_type_for_model(self.model).pk,
            'save_as': self.save_as,
            'save_on_top': self.save_on_top,
            'to_field_var': TO_FIELD_VAR,
            'is_popup_var': IS_POPUP_VAR,
            'app_label': app_label,
        })
        if add and self.add_form_template is not None:
            form_template = self.add_form_template
        else:
            form_template = self.change_form_template

        request.current_app = self.admin_site.name

        return TemplateResponse(request, form_template or [
            "admin/%s/%s/change_form.html" % (app_label, opts.model_name),
            "admin/%s/change_form.html" % app_label,
            "admin/change_form.html"
        ], context)

    def save_model(self, request, obj, form, change):
        if change:
            obj.save()
        else:
            self.model.objects.create(**obj)

    def log_addition(self, *args, **kwargs):
        pass

    def response_add(self, request, obj, post_url_continue=None):
        """
        Determines the HttpResponse for the add_view stage.
        """
        opts = self.model._meta
        pk_value = obj.get('id')
        preserved_filters = self.get_preserved_filters(request)
        msg_dict = {'name': force_text(opts.verbose_name), 'obj': force_text(obj)}
        # Here, we distinguish between different save types by checking for
        # the presence of keys in request.POST.

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            if to_field:
                attr = str(to_field)
            else:
                attr = obj._meta.pk.attname
            value = obj.serializable_value(attr)
            return SimpleTemplateResponse('admin/popup_response.html', {
                'pk_value': escape(pk_value),  # for possible backwards-compatibility
                'value': escape(value),
                'obj': escapejs(obj)
            })

        elif "_continue" in request.POST:
            msg = _('The %(name)s "%(obj)s" was added successfully. You may edit it again below.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            if post_url_continue is None:
                post_url_continue = reverse('admin:%s_%s_change' %
                                            (opts.app_label, opts.model_name),
                                            args=(quote(pk_value),),
                                            current_app=self.admin_site.name)
            post_url_continue = add_preserved_filters(
                {'preserved_filters': preserved_filters, 'opts': opts},
                post_url_continue
            )
            return HttpResponseRedirect(post_url_continue)

        elif "_addanother" in request.POST:
            msg = _('The %(name)s "%(obj)s" was added successfully. You may add another %(name)s below.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.path
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        else:
            msg = _('The %(name)s "%(obj)s" was added successfully.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            return self.response_post_save_add(request, obj)

    def get_object(self, request, object_id, from_field=None):
        """
        Returns an instance matching the field and value provided, the primary
        key is used if no field is provided. Returns ``None`` if no match is
        found or the object_id fails validation.
        """
        model = self.model
        # field = model._meta.pk if from_field is None else model._meta.get_field(from_field)
        # object_id = field.to_python(object_id)
        # assert False, self.model.objects.get(**{'id': object_id})
        # assert False, object_id
        try:
            return self.model.objects.get(**{'id': object_id})
        except (RestException, ValueError):
            return None

    def log_change(self, *args, **kwargs):
        pass

    def response_change(self, request, obj):
        """
        Determines the HttpResponse for the change_view stage.
        """

        if IS_POPUP_VAR in request.POST:
            to_field = request.POST.get(TO_FIELD_VAR)
            attr = str(to_field) if to_field else obj._meta.pk.attname
            # Retrieve the `object_id` from the resolved pattern arguments.
            value = request.resolver_match.args[0]
            new_value = obj.serializable_value(attr)
            return SimpleTemplateResponse('admin/popup_response.html', {
                'action': 'change',
                'value': escape(value),
                'obj': escapejs(obj),
                'new_value': escape(new_value),
            })

        opts = self.model._meta
        pk_value = obj._get_pk_val()
        preserved_filters = self.get_preserved_filters(request)

        msg_dict = {'name': force_text(opts.verbose_name), 'obj': force_text(obj)}
        if "_continue" in request.POST:
            msg = _('The %(name)s "%(obj)s" was changed successfully. You may edit it again below.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.path
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        elif "_saveasnew" in request.POST:
            msg = _('The %(name)s "%(obj)s" was added successfully. You may edit it again below.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = reverse('admin:%s_%s_change' %
                                   (opts.app_label, opts.model_name),
                                   args=(pk_value,),
                                   current_app=self.admin_site.name)
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        elif "_addanother" in request.POST:
            msg = _('The %(name)s "%(obj)s" was changed successfully. You may add another %(name)s below.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = reverse('admin:%s_%s_add' %
                                   (opts.app_label, opts.model_name),
                                   current_app=self.admin_site.name)
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)

        else:
            msg = _('The %(name)s "%(obj)s" was changed successfully.') % msg_dict
            self.message_user(request, msg, messages.SUCCESS)
            return self.response_post_save_change(request, obj)

    @csrf_protect_m
    def delete_view(self, request, object_id, extra_context=None):
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
        deleted_objects, model_count, perms_needed, protected = [obj], {'profile':1}, [], []

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


class InlineRestAdmin(InlineModelAdmin):
    def get_formset(self, request, obj=None, **kwargs):
        assert False, obj
        super(InlineRestAdmin, self).get_formset(request, obj, **kwargs)


class StackedRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/stacked.html'


class TabularRestInline(InlineRestAdmin):
    template = 'admin/edit_inline/tabular.html'
