from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, action
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

META_KEYS = [
    'id', 'uid', 'user', 'version', 'location', 'changeset', 'timestamp',
]


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


@api_view(['POST'])
def reset(request):
    ReplayTool.reset()
    return Response({'message': 'Replay Tool has been successfully reset.'})


class ConflictsViewSet(viewsets.ModelViewSet):
    queryset = conflicting_elements = ConflictingOSMElement.objects.filter(
        local_state=ConflictingOSMElement.LOCAL_STATE_CONFLICTING,
        is_resolved=False,
    )

    def get_serializer_class(self):
        if self.action == 'list':
            return MiniConflictingOSMElementSerializer
        return ConflictingOSMElementSerializer

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'update',
    )
    def update_element(self, request, pk=None):
        osm_element = self.get_object()
        data = self.validate_and_process_data(request.data)
        curr_resolved_data = osm_element.resolved_data or {}
        osm_element.resolved_data = {
            **curr_resolved_data,
            **data
        }
        osm_element.save()
        return Response(ConflictingOSMElementSerializer(osm_element).data)

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'resolve',
    )
    def resolve_element(self, request, pk=None):
        osm_element = self.get_object()
        data = self.validate_and_process_data(request.data)
        curr_resolved_data = osm_element.resolved_data or {}
        osm_element.resolved_data = {
            **curr_resolved_data,
            **data
        }
        osm_element.is_resolved = True
        osm_element.save()
        return Response(ConflictingOSMElementSerializer(osm_element).data)

    def remove_meta_keys(self, data):
        for key in META_KEYS:
            data.pop(key, None)
        return data

    def validate_and_process_data(self, data):
        data = self.remove_meta_keys(data)
        return data
