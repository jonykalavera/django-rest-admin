#!/usr/bin/env python
import os
import sys
import django

from django.conf import settings


def runtests():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.test_settings'
    from django.test.utils import get_runner
    from django.core.management import call_command

    BaseTestRunner = get_runner(settings)  

    if django.VERSION >= (1, 7,):
        django.setup()
        TestRunner = BaseTestRunner
    elif django.VERSION <= (1, 7,):
        class TestRunner(BaseTestRunner):
            def setup_databases(self, **kwargs):
                result = super(TestRunner, self).setup_databases(**kwargs)
                call_command('syncdb', migrate=True, verbosity=0) 
                return result
        settings.INSTALLED_APPS = settings.INSTALLED_APPS + ('tests',)

    test_runner = TestRunner()
    failures = test_runner.run_tests(["tests"])
    sys.exit(bool(failures))

if __name__ == '__main__':
    runtests()
