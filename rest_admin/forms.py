from django import forms


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
        for key, value in self.schema.items():
            field_type = value.get('type', 'str')
            editable = value.get('editable', True)
            if not editable:
                continue
            if field_type == 'int':
                self.fields.update({
                    key: forms.IntegerField(
                        label=value.get('verbose_name', key),
                        required=value.get('required', False)),
                })
            elif field_type == 'email':
                self.fields.update({
                    key: forms.EmailField(
                        label=value.get('verbose_name', key),
                        required=value.get('required', False)),
                })
            elif field_type == 'str':
                required = value.get('required', False)
                choices = value.get('choices', None)
                if choices:
                    if not required:
                        choices = (('', '<Choose>'),) + choices
                    self.fields.update({
                        key: forms.ChoiceField(
                            label=value.get('verbose_name', key),
                            required=required,
                            choices=choices),
                    })
                else:
                    self.fields.update({
                        key: forms.CharField(
                            label=value.get('verbose_name', key),
                            required=value.get('required', False),
                            max_length=512),
                    })

    def save(self, commit=False):
        if self.instance:
            for key, value in self.cleaned_data.items():
                self.instance.data[key] = value
            return self.instance
        return self.cleaned_data

    def save_m2m(self):
        pass
