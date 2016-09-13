from django.contrib import admin

from rest_admin import RestAdmin, StackedRestInline
from .models import Profile, Subscription


class SubscriptionInline(StackedRestInline):
    model = Subscription


class ProfileAdmin(RestAdmin):
    list_display = (
        'email', 'first_name', 'last_name', 'language',
        'created_by', 'created_at', 'modified_by', 'modified_at')
    list_per_page = 25
    inlines = (SubscriptionInline,)

admin.site.register(Profile, ProfileAdmin)
