from django.contrib.admin.widgets import (
    ForeignKeyRawIdWidget, mark_safe, reverse, _, escape, Truncator
)


class ToManyFieldRawIdWidget(ForeignKeyRawIdWidget):
    def render(self, name, value, attrs=None):
        rel_to = self.rel._resource
        if attrs is None:
            attrs = {}
        extra = []
        if rel_to in self.admin_site._registry:
            # The related object is registered with the same AdminSite
            related_url = reverse(
                'admin:%s_%s_changelist' % (
                    rel_to._meta.app_label,
                    rel_to._meta.model_name,
                ),
                current_app=self.admin_site.name,
            )

            params = self.url_parameters()
            if params:
                url = '?' + '&amp;'.join('%s=%s' % (k, v) for k, v in params.items())
            else:
                url = ''
            if "class" not in attrs:
                attrs['class'] = 'vForeignKeyRawIdAdminField'  # The JavaScript code looks for this hook.
            # TODO: "lookup_id_" is hard-coded here. This should instead use
            # the correct API to determine the ID dynamically.
            extra.append('<a href="%s%s" class="related-lookup" id="lookup_id_%s" title="%s"></a>' %
                (related_url, url, name, _('Lookup')))
        output = [super(ForeignKeyRawIdWidget, self).render(name, value, attrs)] + extra
        if value:
            output.append(self.label_for_value(value))
        return mark_safe(''.join(output))

    def url_parameters(self):
        return {}

    def label_for_value(self, value):
        key = self.rel.name
        try:
            obj = self.rel._resource._default_manager.get(**{key: value})
            return '&nbsp;<strong>%s</strong>' % escape(
                Truncator(obj).words(14, truncate='...'))
        except (ValueError, self.rel._resource.DoesNotExist):
            return ''
