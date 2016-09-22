from django.contrib.admin.apps import SimpleAdminConfig
from django.core.exceptions import FieldDoesNotExist
from django.contrib.admin import checks
from django.db import models

from restorm.fields.related import RelatedResource
from rest_admin.forms import BaseRestForm


class RestAdminConfig(SimpleAdminConfig):
    """Custom AppConfig for rest_admin which does autodiscovery."""
    name = 'rest_admin'
    verbose_name = 'Rest Admin'

    def patch_default_admin_site(self):
        from django.contrib import admin
        admin.site = self.module.site

    def patch_system_checks(self):
        def _check_raw_id_fields_item(self, cls, model, field_name, label):
            """ Check an item of `raw_id_fields`, i.e. check that field named
            `field_name` exists in model `model` and is a ForeignKey or a
            ManyToManyField. """
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist:
                return checks.refer_to_missing_field(
                    field=field_name, option=label,
                    model=model, obj=cls, id='admin.E002')
            else:
                if not isinstance(field, (
                        models.ForeignKey, models.ManyToManyField,
                        RelatedResource)):
                    return checks.must_be(
                        'a ForeignKey, ManyToManyField, RelatedResource',
                        option=label, obj=cls, id='admin.E003')
                else:
                    return []

        checks.ModelAdminChecks._check_raw_id_fields_item = \
            _check_raw_id_fields_item
        checks.InlineModelAdminChecks._check_raw_id_fields_item = \
            _check_raw_id_fields_item

        def _check_form(self, cls, model):
            """ Check that form subclasses BaseModelForm. """

            if hasattr(cls, 'form') and not issubclass(
                    cls.form, (checks.BaseModelForm, BaseRestForm)):
                return checks.must_inherit_from(
                    parent='BaseModelForm or BaseRestForm', option='form',
                    obj=cls, id='admin.E016')
            else:
                return []

        checks.ModelAdminChecks._check_form = _check_form
        checks.InlineModelAdminChecks._check_form = _check_form

    def ready(self):
        self.patch_default_admin_site()
        self.patch_system_checks()
        super(RestAdminConfig, self).ready()
        self.module.autodiscover()
