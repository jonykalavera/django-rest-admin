from collections import OrderedDict
from restorm.resource import Resource

from .client import profiles_client


class Profile(Resource):
    class Meta:
        resource_name = 'profile'
        list = r'^profiles/$'
        item = r'^profiles/(?P<id>\d)/$'
        client = profiles_client
        schema = OrderedDict([
            ('id', {
                'type': 'int',
                'primary': True,
                'editable': False
            }),
            ('email', {
                'type': 'str',
                'required': True
            }),
            ('first_name', {
                'type': 'str',
                'required': False,
                'verbose_name': 'First name'
            }),
            ('last_name', {
                'type': 'str',
                'required': False,
                'verbose_name': 'Last name'
            }),
            ('language', {
                'type': 'str',
                'required': True,
                'choices': (
                    ('en', 'English'),
                    ('es', 'Spanish'),
                )
            }),
            ('subscription', {
                'type': 'list',
                'required': False
            }),
            ('created_by', {
                'type': 'str',
                'editable': False
            }),
            ('created_at', {
                'type': 'str',
                'editable': False
            }),
            ('modified_by', {
                'type': 'str',
                'editable': False
            }),
            ('modified_at', {
                'type': 'str',
                'editable': False
            })
        ])
