#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
from setuptools import setup, find_packages


def read_file(filename):
    """Read a file into a string"""
    path = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.join(path, filename)
    try:
        return open(filepath).read()
    except IOError:
        return ''

setup(
    name='rest_admin',
    version='1.0.0',
    description='Django Admin extensions to add resources from Restful APIs.',
    test_suite = 'runtests.runtests',
    author='National Geographic Society',
    packages=find_packages(),
    classifiers=[
        'Framework :: Django',
        'Environment :: Web Environment',
        'Program Language :: Python',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules'],
    include_package_data=True,
    zip_safe=False,
    install_requires=read_file('requirements.txt'),
)
