# Generated by Django 2.2.8 on 2019-12-18 11:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('replay_tool', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conflictingosmelement',
            name='local_action',
        ),
        migrations.AddField(
            model_name='conflictingosmelement',
            name='local_state',
            field=models.CharField(choices=[('added', 'Added'), ('deleted', 'Deleted'), ('modified', 'Modified'), ('conflicting', 'Conflicting')], default='modified', max_length=15),
            preserve_default=False,
        ),
    ]
