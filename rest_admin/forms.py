from django import forms
from restorm import fields

from .widgets import ToManyFieldRawIdWidget


class RestForm(forms.Form):
    def __init__(self, *args, **kwargs):
        # self.initial = kwargs.get('initial', {})
        # kwargs.pop('initial', None)
        self.instance = kwargs.get('instance', None)
        if self.instance:
            self.initial = self.instance.data.__dict__.get('_obj')
            kwargs['initial'] = self.initial
        kwargs.pop('instance', None)
        super(RestForm, self).__init__(*args, **kwargs)
        for name, field in self.resource._meta._fields.items():
            if not field.editable:
                continue
            label = field.verbose_name.capitalize()
            if isinstance(field, fields.IntegerField):
                self.fields.update({
                    name: forms.IntegerField(
                        label=label, required=field.required),
                })
            elif isinstance(field, fields.URLField):
                self.fields.update({
                    name: forms.URLField(
                        label=label,
                        required=field.required,
                        max_length=field.max_length or 255),
                })
            elif isinstance(field, fields.BooleanField):
                self.fields.update({
                    name: forms.BooleanField(
                        label=label,
                        required=field.required),
                })
            elif isinstance(field, fields.CharField):
                if field.choices:
                    choices = field.choices
                    if not field.required:
                        choices = (('', '<Choose>'),) + choices
                    self.fields.update({
                        name: forms.ChoiceField(
                            label=label,
                            required=field.required,
                            choices=choices),
                    })
                else:
                    self.fields.update({
                        name: forms.CharField(
                            label=label,
                            required=field.required,
                            max_length=field.max_length or 255),
                    })
            elif isinstance(field, fields.ToOneField):
                if not name in self.admin.raw_id_fields:
                    choices = [
                        (o.id, o.__unicode__())
                        for o in field._resource.objects.all()]
                    if not field.required:
                        choices = (('', '<Choose>'),) + choices
                    self.fields.update({
                        name: forms.ChoiceField(
                            label=label,
                            required=field.required,
                            choices=choices),
                    })
                else:
                    self.fields.update({
                        name: ToManyFieldRawIdWidget(field, self.admin),
                    })

    def save(self, commit=False):
        if self.instance:
            for key, value in self.cleaned_data.items():
                self.instance.data[key] = value
            return self.instance
        return self.cleaned_data

    def save_m2m(self):
        pass
