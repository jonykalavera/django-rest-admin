from django.contrib.admin.apps import SimpleAdminConfig


class RestAdminConfig(SimpleAdminConfig):
    """Custom AppConfig for rest_admin which does autodiscovery."""
    name = 'rest_admin'
    verbose_name = 'Rest Admin'

    def patch_default_admin_site(self):
        from django.contrib import admin
        admin.site = self.module.site

    def ready(self):
        self.patch_default_admin_site()
        super(RestAdminConfig, self).ready()
        self.module.autodiscover()
