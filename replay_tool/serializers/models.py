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
            'local_changesets_count': LocalChangeSet.objects.count(),
            'local_elements_count': obj.elements_data.get('local'),
            'upstream_elements_count': obj.elements_data.get('upstream'),
        }


class ConflictingOSMElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConflictingOSMElement
        exclude = ('resolved_data', 'local_data', 'upstream_data')
