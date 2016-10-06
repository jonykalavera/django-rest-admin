from django.contrib.admin.widgets import ForeignKeyRawIdWidget, ManyToManyRawIdWidget
from restorm.resource import Resource


class ToOneFieldRawIdWidget(ForeignKeyRawIdWidget):
    def render(self, name, value, attrs=None):
        if isinstance(value, Resource):
            value = value.pk
        return super(ToOneFieldRawIdWidget, self).render(name, value, attrs)


class ToManyFieldRawIdWidget(ManyToManyRawIdWidget):
    pass
