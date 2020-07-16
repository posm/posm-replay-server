# Generated by Django 2.2.13 on 2020-07-16 05:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('replay_tool', '0009_replaytoolconfig'),
    ]

    operations = [
        migrations.AlterField(
            model_name='osmelement',
            name='status',
            field=models.CharField(choices=[('resolved', 'Resolved'), ('partially_resolved', 'Partially Resolved'), ('unresolved', 'Unresolved'), ('pushed', 'Pushed')], max_length=25),
        ),
        migrations.AlterField(
            model_name='replaytool',
            name='state',
            field=models.CharField(choices=[('not_triggered', 'Not Triggered'), ('gathering_changesets', 'Gathering Changesets'), ('extracting_local_aoi', 'Extracting Local Aoi'), ('extracting_upstream_aoi', 'Extracting Upstream Aoi'), ('detecting_conflicts', 'Detecting Conflicts'), ('creating_geojsons', 'Creating GeoJSONs'), ('resolving_conflicts', 'Resolving Conflicts'), ('pushing_conflicts', 'Push Conflicts')], default='not_triggered', max_length=100),
        ),
    ]