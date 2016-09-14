from django import forms
from restorm import fields


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
            label = field.verbose_name or name
            if isinstance(field, fields.IntegerField):
                self.fields.update({
                    name: forms.IntegerField(
                        label=label, required=field.required),
                })
            if isinstance(field, fields.URLField):
                self.fields.update({
                    name: forms.URLField(
                        label=label,
                        required=field.required,
                        max_length=field.max_length or 255),
                })
            # elif field_type == 'email':
            #     self.fields.update({
            #         key: forms.EmailField(
            #             label=value.get('verbose_name', key),
            #             required=value.get('required', False)),
            #     })
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

    def save(self, commit=False):
        if self.instance:
            for key, value in self.cleaned_data.items():
                self.instance.data[key] = value
            return self.instance
        return self.cleaned_data

    def save_m2m(self):
        pass
