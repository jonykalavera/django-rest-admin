from django.forms.fields import TypedChoiceField
from django.utils.functional import SimpleLazyObject


class ResourceChoiceField(TypedChoiceField):
    def __init__(self, queryset, **kwargs):
        kwargs['choices'] = SimpleLazyObject(lambda: [(obj.pk, unicode(obj)) for obj in queryset])
        super(ResourceChoiceField, self).__init__(**kwargs)
