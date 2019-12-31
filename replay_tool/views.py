from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework import viewsets, exceptions
from rest_framework.response import Response


from .tasks import task_prepare_data_for_replay_tool

from .models import ReplayTool, OSMElement
from .serializers.models import (
    ReplayToolSerializer,
    OSMElementSerializer,
    MiniOSMElementSerializer,
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
        task_prepare_data_for_replay_tool.delay()
        return Response({'message': 'ReplayTool has been successfully triggered.'})
    raise exceptions.ValidationError('Already triggered.')


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
    queryset = OSMElement.get_conflicting_elements()

    def get_serializer_class(self):
        if self.action == 'list':
            return MiniOSMElementSerializer
        return OSMElementSerializer

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
            **data,
            'id': osm_element.element_id
        }
        osm_element.status = OSMElement.STATUS_PARTIALLY_RESOLVED
        osm_element.save()
        return Response(OSMElementSerializer(osm_element).data)

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
        osm_element.status = OSMElement.STATUS_RESOLVED
        osm_element.save()
        if OSMElement.get_conflicting_elements().count() == 0:
            replay_tool = ReplayTool.objects.get()
            replay_tool.state = ReplayTool.STATUS_RESOLVED
            replay_tool.save()
        return Response(OSMElementSerializer(osm_element).data)

    def remove_meta_keys(self, data):
        for key in META_KEYS:
            data.pop(key, None)
        return data

    def validate_and_process_data(self, data):
        data = self.remove_meta_keys(data)
        return data
