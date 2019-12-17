from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.response import Response


from .tasks import task_prepare_data_for_replay_tool

from .models import ReplayTool, ConflictingOSMElement
from .serializers.models import (
    ReplayToolSerializer,
    ConflictingOSMElementSerializer,
    MiniConflictingOSMElementSerializer,
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


class ConflictsViewSet(viewsets.ModelViewSet):
    queryset = conflicting_elements = ConflictingOSMElement.objects.filter(
        local_action=ConflictingOSMElement.LOCAL_ACTION_MODIFIED
    )

    def get_serializer_class(self):
        if self.action == 'list':
            return MiniConflictingOSMElementSerializer
        return ConflictingOSMElementSerializer
