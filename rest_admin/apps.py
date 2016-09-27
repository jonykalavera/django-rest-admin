from django.contrib.admin.apps import SimpleAdminConfig
from django.core.exceptions import FieldDoesNotExist
from django.contrib.admin import checks
from django.db import models

from restorm.resource import Resource
from restorm.fields.related import RelatedResource
from rest_admin import forms as rest_admin_forms


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
                    cls.form, (checks.BaseModelForm, rest_admin_forms.BaseRestForm)):
                return checks.must_inherit_from(
                    parent='BaseModelForm or BaseRestForm', option='form',
                    obj=cls, id='admin.E016')
            else:
                return []

        checks.ModelAdminChecks._check_form = _check_form
        checks.InlineModelAdminChecks._check_form = _check_form

        def _check_inlines_item(self, cls, model, inline, label):
            """ Check one inline model admin. """
            inline_label = '.'.join([inline.__module__, inline.__name__])

            from django.contrib.admin.options import BaseModelAdmin

            if not issubclass(inline, BaseModelAdmin):
                return [
                    checks.Error(
                        "'%s' must inherit from 'BaseModelAdmin'." % inline_label,
                        hint=None,
                        obj=cls,
                        id='admin.E104',
                    )
                ]
            elif not inline.model:
                return [
                    checks.Error(
                        "'%s' must have a 'model' attribute." % inline_label,
                        hint=None,
                        obj=cls,
                        id='admin.E105',
                    )
                ]
            elif not issubclass(inline.model, (models.Model, Resource)):
                return checks.must_be('a Model', option='%s.model' % inline_label,
                               obj=cls, id='admin.E106')
            else:
                return inline.check(model)
        checks.ModelAdminChecks._check_inlines_item = _check_inlines_item

        def _check_relation(self, cls, parent_model):
            if issubclass(parent_model, Resource):
                try:
                    rest_admin_forms._get_foreign_key(parent_model, cls.model, fk_name=cls.fk_name)
                except ValueError as e:
                    return [checks.Error(e.args[0], hint=None, obj=cls, id='admin.E202')]
                else:
                    return []
            else:
                try:
                    checks._get_foreign_key(parent_model, cls.model, fk_name=cls.fk_name)
                except ValueError as e:
                    return [checks.Error(e.args[0], hint=None, obj=cls, id='admin.E202')]
                else:
                    return []
        checks.InlineModelAdminChecks._check_relation = _check_relation

    def ready(self):
        self.patch_default_admin_site()
        self.patch_system_checks()
        super(RestAdminConfig, self).ready()
        self.module.autodiscover()
