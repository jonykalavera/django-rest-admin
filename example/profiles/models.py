from restorm.resource import Resource
from restorm import fields
from .client import profiles_client


class Profile(Resource):
    LANGUAGE_CHOICES = (
        ('en', 'English'),
        ('es', 'Spanish'),
    )
    id = fields.IntegerField(primary=True, editable=False)
    email = fields.CharField()
    first_name = fields.CharField(verbose_name="First Name", required=False)
    last_name = fields.CharField(verbose_name="Last Name", required=False)
    language = fields.CharField(required=True, choices=LANGUAGE_CHOICES)

    created_by = fields.CharField(editable=False)
    created_at = fields.CharField(editable=False)
    modified_by = fields.CharField(editable=False)
    modified_at = fields.CharField(editable=False)

    class Meta:
        resource_name = 'profile'
        list = r'^profiles/$'
        item = r'^profiles/(?P<id>\d)/$'
        client = profiles_client


class Subscription(Resource):
    VENDOR_CHOICES = (
        ('smartfocus', 'Smart Focus'),
    )
    id = fields.IntegerField(primary=True, editable=False)
    profile = fields.RelatedResource('profile', Profile)
    vendor_slug = fields.CharField(required=True, choices=VENDOR_CHOICES)
    vendor_name = fields.CharField(editable=False)
    enabled = fields.BooleanField(default=True)

    created_by = fields.CharField(editable=False)
    created_at = fields.CharField(editable=False)
    modified_by = fields.CharField(editable=False)
    modified_at = fields.CharField(editable=False)

    class Meta:
        resource_name = 'subscription'
        list = r'^subscriptions/$'
        item = r'^subscriptions/(?P<id>\d)/$'
        client = profiles_client
