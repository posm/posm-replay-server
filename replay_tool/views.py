from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from replay_tool.utils.common import (
    get_current_aoi_bbox, get_aoi_name,
    get_aoi_created_datetime,
)

from .models import (
    LocalChangeSet,
    ReplayTool,
    ConflictingNode,
    ConflictingWay,
    ConflictingRelation,
)
from .serializers import (
    ReplayToolSerializer,
    ConflictingNodeSerializer,
    ConflictingWaySerializer,
    ConflictingRelationSerializer,
)


class ReplayToolViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReplayToolSerializer
    queryset = ReplayTool.objects.all()


class CurrentAOIView(APIView):
    def get(self, request, version=None, format=None):
        tool = ReplayTool.objects.get()
        aoi = {
            'name': get_aoi_name(exception_if_not_set=True),
            'bounds': get_current_aoi_bbox(),
            'date_cloned': get_aoi_created_datetime(),
            'local_changesets_count': LocalChangeSet.objects.count(),
            'local_elements_count': tool.elements_data.get('local'),
            'upstream_elements_count': tool.elements_data.get('upstream'),
        }
        return Response(aoi)


class ConflictsView(APIView):
    def get(self, request, version=None, format=None):
        node_conflicts = ConflictingNode.objects.filter(local_action=ConflictingNode.LOCAL_ACTION_MODIFIED)
        way_conflicts = ConflictingWay.objects.filter(local_action=ConflictingWay.LOCAL_ACTION_MODIFIED)
        relation_conflicts = ConflictingRelation.objects.filter(local_action=ConflictingRelation.LOCAL_ACTION_MODIFIED)

        return Response({
            'nodes': ConflictingNodeSerializer(node_conflicts, many=True).data,
            'ways': ConflictingWaySerializer(way_conflicts, many=True).data,
            'relations': ConflictingRelationSerializer(relation_conflicts, many=True).data,
        })
