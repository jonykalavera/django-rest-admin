from django.apps import AppConfig
from restorm.conf import settings as restorm_settings

from .client import profiles_client


class ProfilesConfig(AppConfig):
    name = 'profiles'
    verbose_name = 'Profiles'

    def set_default_client(self):
        restorm_settings.DEFAULT_CLIENT = profiles_client

    def ready(self):
        self.set_default_client()
