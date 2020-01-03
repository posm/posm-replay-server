from rest_framework import serializers

from replay_tool.models import ReplayTool, LocalChangeSet, OSMElement

from replay_tool.utils.common import (
    get_current_aoi_info, get_aoi_name,
    get_aoi_created_datetime,
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
    name = serializers.SerializerMethodField()
    local_geojson = serializers.SerializerMethodField()
    upstream_geojson = serializers.SerializerMethodField()

    class Meta:
        model = OSMElement
        exclude = ('local_data', 'upstream_data')

    def get_local_geojson(self, obj):
        if obj.local_state == OSMElement.LOCAL_STATE_REFERRING:
            local_geojson = dict(obj.local_geojson)
            local_geojson['properties'] = dict(obj.local_geojson['properties'])
            # Add referenced nodes
            local_geojson['properties']['conflicting_nodes'] = {
                x.element_id: x.local_data['location']
                for x in obj.referenced_elements.all()
            }
            return local_geojson
        else:
            return obj.local_geojson

    def get_upstream_geojson(self, obj):
        if obj.local_state == OSMElement.LOCAL_STATE_REFERRING:
            upstream_geojson = dict(obj.upstream_geojson)
            upstream_geojson['properties'] = dict(obj.upstream_geojson['properties'])
            # Add referenced nodes
            upstream_geojson['properties']['conflicting_nodes'] = {
                x.element_id: x.upstream_data['location']
                for x in obj.referenced_elements.all()
            }
            return upstream_geojson
        else:
            return obj.local_geojson

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
