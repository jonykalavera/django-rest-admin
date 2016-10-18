from django.utils.module_loading import autodiscover_modules

from rest_admin.options import RestAdmin, StackedRestInline, TabularRestInline,\
    NestedStackedInline, NestedTabularInline
from rest_admin.sites import RestAdminSite, site


__all__ = [
    "RestAdminSite", "autodiscover",
    "RestAdmin", "StackedRestInline", "TabularRestInline", "NestedStackedInline",
    "NestedTabularInline"
]


def autodiscover():
    autodiscover_modules('admin', register_to=site)


default_app_config = 'rest_admin.apps.RestAdminConfig'
