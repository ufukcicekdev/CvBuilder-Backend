# Generated by Django 5.1.6 on 2025-03-01 22:35

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cvs", "0004_alter_certificate_options_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Certificate",
        ),
    ]
