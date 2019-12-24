from rest_framework import serializers

from replay_tool.models import ReplayTool, LocalChangeSet, OSMElement
from copy import deepcopy

from replay_tool.utils.common import (
    get_current_aoi_info, get_aoi_name,
    get_aoi_created_datetime,
    transform_tags_to_dict,
)


class ReplayToolSerializer(serializers.ModelSerializer):
    aoi = serializers.SerializerMethodField()

    class Meta:
        model = ReplayTool
        exclude = ('elements_data',)

    def get_aoi(self, obj):
        aoi_info = get_current_aoi_info()
        return {
            'name': get_aoi_name(exception_if_not_set=True),
            'bounds': aoi_info['bbox'],
            'description': aoi_info['description'],
            'date_cloned': get_aoi_created_datetime(),
            'total_conflicting_elements': OSMElement.get_conflicting_elements().count(),
            'total_resolved_elements': OSMElement.get_resolved_elements().count(),
            'local_changesets_count': LocalChangeSet.objects.count(),
            'local_elements_count': obj.elements_data.get('local'),
            'upstream_elements_count': obj.elements_data.get('upstream'),
        }


class OSMElementSerializer(serializers.ModelSerializer):
    current_geojson = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = OSMElement
        exclude = ('resolved_data', 'local_data', 'upstream_data')

    def get_current_geojson(self, obj):
        geojson = deepcopy(obj.local_geojson)
        # If there is not resolved data, send local data
        # Because initially revolved_data and local data are same
        # After conflicting element is partially updated, data is available in
        # 'resolved_data' field
        properties = obj.resolved_data or deepcopy(obj.local_data)
        properties['tags'] = transform_tags_to_dict(properties.get('tags', []))
        geojson['properties'] = properties
        return geojson

    def get_name(self, obj):
        tags = {x['k']: x['v'] for x in obj.local_data.get('tags', [])}
        if not tags or not tags.get('name'):
            return f'{obj.type} id {obj.element_id}'
        return tags['name']


class MiniOSMElementSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = OSMElement
        fields = ('id', 'element_id', 'type', 'name')

    def get_name(self, obj):
        tags = {x['k']: x['v'] for x in obj.local_data.get('tags', [])}
        if not tags or not tags.get('name'):
            return f'{obj.type} id {obj.element_id}'
        return tags['name']
