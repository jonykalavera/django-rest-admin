from django.contrib.admin.utils import _get_non_gfk_field, FieldDoesNotExist


def lookup_field(name, obj, model_admin=None):
    opts = model_admin.model._meta
    try:
        f = _get_non_gfk_field(opts, name)
    except FieldDoesNotExist:
        # For non-field values, the value is either a method, property or
        # returned via a callable.
        if callable(name):
            attr = name
            value = attr(obj)
        elif (model_admin is not None and
                hasattr(model_admin, name) and
                not name == '__str__' and
                not name == '__unicode__'):
            attr = getattr(model_admin, name)
            value = attr(obj)
        else:
            attr = getattr(obj, name)
            if callable(attr):
                value = attr()
            else:
                value = attr
        f = None
    else:
        attr = None
        value = getattr(obj, name)
    return f, attr, value
