from rest_framework import serializers

from replay_tool.models import ReplayTool, LocalChangeSet, ConflictingOSMElement

from replay_tool.utils.common import (
    get_current_aoi_bbox, get_aoi_name,
    get_aoi_created_datetime,
)


class ReplayToolSerializer(serializers.ModelSerializer):
    aoi = serializers.SerializerMethodField()

    class Meta:
        model = ReplayTool
        exclude = ('elements_data',)

    def get_aoi(self, obj):
        return {
            'name': get_aoi_name(exception_if_not_set=True),
            'bounds': get_current_aoi_bbox(),
            'date_cloned': get_aoi_created_datetime(),
            'total_conflicting_elements': ConflictingOSMElement.objects.filter(
                is_resolved=False
            ).count(),
            'local_changesets_count': LocalChangeSet.objects.count(),
            'local_elements_count': obj.elements_data.get('local'),
            'upstream_elements_count': obj.elements_data.get('upstream'),
        }


class ConflictingOSMElementSerializer(serializers.ModelSerializer):
    current_geojson = serializers.SerializerMethodField()

    class Meta:
        model = ConflictingOSMElement
        exclude = ('resolved_data', 'local_data', 'upstream_data')

    def get_current_geojson(self, obj):
        geojson = dict(obj.local_geojson)
        properties = obj.resolved_data
        geojson['properties'] = properties
        return geojson


class MiniConflictingOSMElementSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = ConflictingOSMElement
        fields = ('id', 'element_id', 'type', 'name')

    def get_name(self, obj):
        tags = {x['k']: x['v'] for x in obj.local_data.get('tags', [])}
        if not tags or not tags.get('name'):
            return f'{obj.type} id {obj.element_id}'
        return tags['name']
