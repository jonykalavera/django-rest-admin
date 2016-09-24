import sys
from django.contrib.admin.utils import _get_non_gfk_field, FieldDoesNotExist
from django.utils import six
from django.utils.importlib import import_module


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


class patch(object):
    def __init__(self, dotted_path, new):
        self._dotted_path = dotted_path
        self._new = new
        try:
            module_path, class_name = self._dotted_path.rsplit('.', 1)
        except ValueError:
            msg = "%s doesn't look like a module path" % dotted_path
            six.reraise(ImportError, ImportError(msg), sys.exc_info()[2])
        self._module_path = module_path
        self._class_name = class_name
        self._module = import_module(self._module_path)
        try:
            self._old = getattr(self._module, self._class_name)
        except AttributeError:
            msg = 'Module "%s" does not define a "%s" attribute/class' % (
                self._module_path, self._class_name)
            six.reraise(ImportError, ImportError(msg), sys.exc_info()[2])

    def __enter__(self):
        setattr(self._module, self._class_name, self._new)
        return self._new

    def __exit__(self, type, value, traceback):
        setattr(self._module, self._class_name, self._old)
