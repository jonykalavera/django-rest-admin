from django.contrib.admin.widgets import (
    mark_safe, RelatedFieldWidgetWrapper,
    CASCADE, render_to_string, force_text
)
from django.contrib.admin.widgets import \
    ForeignKeyRawIdWidget, ManyToManyRawIdWidget
from restorm.resource import Resource


class RelatedResourceWidgetWrapper(RelatedFieldWidgetWrapper):
    def __init__(self, widget, rel, admin_site, can_add_related=None,
                 can_change_related=False, can_delete_related=False):
        self.needs_multipart_form = widget.needs_multipart_form
        self.attrs = widget.attrs
        self.choices = widget.choices
        self.widget = widget
        self.rel = rel
        # Backwards compatible check for whether a user can add related
        # objects.
        if can_add_related is None:
            can_add_related = rel in admin_site._registry
        self.can_add_related = can_add_related
        # XXX: The UX does not support multiple selected values.
        multiple = getattr(widget, 'allow_multiple_selected', False)
        self.can_change_related = not multiple and can_change_related
        # XXX: The deletion UX can be confusing when dealing with cascading deletion.
        cascade = getattr(rel, 'on_delete', None) is CASCADE
        self.can_delete_related = not multiple and not cascade and can_delete_related
        # so we can check if the related object is registered with this AdminSite
        self.admin_site = admin_site

    def render(self, name, value, *args, **kwargs):
        from django.contrib.admin.views.main import IS_POPUP_VAR, TO_FIELD_VAR
        rel_opts = self.rel._meta
        info = (rel_opts.app_label, rel_opts.model_name)
        self.widget.choices = self.choices
        url_params = '&'.join("%s=%s" % param for param in [
            (TO_FIELD_VAR, self.rel.name),
            (IS_POPUP_VAR, 1),
        ])
        context = {
            'widget': self.widget.render(name, value, *args, **kwargs),
            'name': name,
            'url_params': url_params,
            'model': rel_opts.verbose_name,
        }
        if self.can_change_related:
            change_related_template_url = self.get_related_url(info, 'change', '__fk__')
            context.update(
                can_change_related=True,
                change_related_template_url=change_related_template_url,
            )
        if self.can_add_related:
            add_related_url = self.get_related_url(info, 'add')
            context.update(
                can_add_related=True,
                add_related_url=add_related_url,
            )
        if self.can_delete_related:
            delete_related_template_url = self.get_related_url(info, 'delete', '__fk__')
            context.update(
                can_delete_related=True,
                delete_related_template_url=delete_related_template_url,
            )
        return mark_safe(render_to_string(self.template, context))


class ToOneFieldRawIdWidget(ForeignKeyRawIdWidget):
    def render(self, name, value, attrs=None):
        if isinstance(value, Resource):
            value = value.pk
        return super(ToOneFieldRawIdWidget, self).render(name, value, attrs)


class ToManyFieldRawIdWidget(ManyToManyRawIdWidget):
    """
    A Widget for displaying ManyToMany ids in the "raw_id" interface rather than
    in a <select multiple> box.
    """
    def render(self, name, value, attrs=None):
        if attrs is None:
            attrs = {}
        if self.rel.to in self.admin_site._registry:
            # The related object is registered with the same AdminSite
            attrs['class'] = 'vManyToManyRawIdAdminField'
        if value:
            value = ','.join(force_text(v) for v in value)
        else:
            value = ''
        return super(ToManyFieldRawIdWidget, self).render(name, value, attrs)

    def url_parameters(self):
        return self.base_url_parameters()

    def label_for_value(self, value):
        return ''

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        if value:
            return value.split(',')
