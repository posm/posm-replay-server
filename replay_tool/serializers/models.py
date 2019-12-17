from rest_framework import serializers

from replay_tool.models import ReplayTool, LocalChangeSet

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
            'local_changesets_count': LocalChangeSet.objects.count(),
            'local_elements_count': obj.elements_data.get('local'),
            'upstream_elements_count': obj.elements_data.get('upstream'),
        }


class ConflictingElementSerializer(serializers.Serializer):
    local_geojson = serializers.SerializerMethodField()
    upstream_geojson = serializers.SerializerMethodField()

    def get_geojson(self, obj):
        return obj.geojson


class ConflictingNodeSerializer(ConflictingElementSerializer):
    node_id = serializers.IntegerField(read_only=True)

    class Meta:
        fields = ('id', 'node_id', 'geojson', 'is_resolved')


class ConflictingWaySerializer(ConflictingElementSerializer):
    way_id = serializers.IntegerField(read_only=True)

    class Meta:
        fields = ('id', 'way_id', 'geojson', 'is_resolved')


class ConflictingRelationSerializer(ConflictingElementSerializer):
    relation_id = serializers.IntegerField(read_only=True)

    class Meta:
        fields = ('id', 'relation_id', 'geojson', 'is_resolved')
