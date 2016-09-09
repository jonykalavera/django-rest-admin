from django.contrib import admin

from rest_admin import RestAdmin
from .models import Profile


class ProfileAdmin(RestAdmin):
    list_display = (
        'email', 'first_name', 'last_name', 'language',
        'created_by', 'created_at', 'modified_by', 'modified_at')
    list_per_page = 25

admin.site.register(Profile, ProfileAdmin)
