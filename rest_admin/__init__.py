from django.utils.module_loading import autodiscover_modules

from rest_admin.options import RestAdmin, StackedRestInline, TabularRestInline
from rest_admin.nested import NestedRestAdmin, NestedStackedInline, NestedTabularInline
from rest_admin.sites import RestAdminSite, site


__all__ = [
    "RestAdminSite", "autodiscover",
    "RestAdmin", "StackedRestInline", "TabularRestInline",
    "NestedRestAdmin", "NestedStackedInline", "NestedTabularInline"
]


def autodiscover():
    autodiscover_modules('admin', register_to=site)


default_app_config = 'rest_admin.apps.RestAdminConfig'
