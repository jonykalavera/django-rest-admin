# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import wham.fields


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='WhamProfile',
            fields=[
                ('id', wham.fields.WhamIntegerField(serialize=False, primary_key=True)),
                ('email', wham.fields.WhamCharField(unique=True, max_length=255)),
                ('first_name', wham.fields.WhamCharField(max_length=255)),
                ('last_name', wham.fields.WhamCharField(max_length=255)),
                ('language', wham.fields.WhamCharField(max_length=255)),
                ('created_at', wham.fields.WhamDateTimeField()),
                ('created_by', wham.fields.WhamCharField(max_length=255)),
                ('modified_at', wham.fields.WhamDateTimeField()),
                ('modified_by', wham.fields.WhamCharField(max_length=255)),
            ],
            options={
                'db_table': 'profiles_profile',
            },
        ),
    ]
