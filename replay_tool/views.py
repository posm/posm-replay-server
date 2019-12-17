from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response


from .tasks import task_prepare_data_for_replay_tool

from .models import (
    ReplayTool,
    ConflictingNode,
    ConflictingWay,
    ConflictingRelation,
)
from .serializers.models import (
    ReplayToolSerializer,
    ConflictingNodeSerializer,
    ConflictingWaySerializer,
    ConflictingRelationSerializer,
)


class ReplayToolView(APIView):
    def get(self, request, version=None, format=None):
        tool = ReplayTool.objects.get()
        return Response(ReplayToolSerializer(tool).data)


@api_view(['POST'])
def trigger(request):
    tool = ReplayTool.objects.get()
    if not tool.is_initiated:
        ReplayTool.reset()
        task_prepare_data_for_replay_tool.delay()
        return Response({'message': 'ReplayTool has been successfully triggered.'})
    return Response({'message': 'Replay Tool has already been triggered.'})


@api_view(['POST'])
def retrigger(request):
    ReplayTool.reset()
    task_prepare_data_for_replay_tool.delay()
    return Response({'message': 'Replay Tool has been successfully re-triggered.'})


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
