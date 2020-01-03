from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework import viewsets, exceptions
from rest_framework.response import Response


from .tasks import task_prepare_data_for_replay_tool, create_and_push_changeset

from .models import ReplayTool, OSMElement
from .serializers.models import (
    ReplayToolSerializer,
    OSMElementSerializer,
    MiniOSMElementSerializer,
)

META_KEYS = [
    'id', 'uid', 'user', 'version', 'changeset', 'timestamp',
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


@api_view(['POST'])
def push_upstream(request):
    data = request.data
    oauth_token = data.get('oauth_token')
    oauth_token_secret = data.get('oauth_token_secret')
    if not oauth_token:
        raise exceptions.ValidationError({'oauth_token': 'This field must be present.'})
    if not oauth_token_secret:
        raise exceptions.ValidationError({'oauth_token_secret': 'This field must be present.'})
    # Check for replay tool's status
    replay_tool = ReplayTool.objects.get()
    if replay_tool.state != ReplayTool.STATUS_RESOLVED:
        raise exceptions.ValidationError('All the conflicts have not been resolved')

    # Call the task
    replay_tool.state = ReplayTool.STATUS_PUSH_CONFLICTS
    replay_tool.save()
    create_and_push_changeset.delay(oauth_token, oauth_token_secret)
    return Response({
        'message': 'The changes are being pushed upstream'
    })


class ConflictsViewSet(viewsets.ModelViewSet):
    queryset = OSMElement.get_all_conflicting_elements()

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
        data = self.validate_and_process_data(request.data, osm_element)

        curr_resolved_data = osm_element.resolved_data or {}
        osm_element.resolved_data = {
            **curr_resolved_data,
            **data,
            'id': osm_element.element_id
        }
        osm_element.status = OSMElement.STATUS_PARTIALLY_RESOLVED
        osm_element.save()

        # Update the referenced elements
        update_referenced_elements(osm_element)

        return Response(OSMElementSerializer(osm_element).data)

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'resolve',
    )
    def resolve_element(self, request, pk=None):
        osm_element = self.get_object()
        data = self.validate_and_process_data(request.data, osm_element)

        curr_resolved_data = osm_element.resolved_data or {}
        osm_element.resolved_data = {
            **curr_resolved_data,
            **data,
            'id': osm_element.element_id
        }
        osm_element.status = OSMElement.STATUS_RESOLVED
        osm_element.save()
        # Resolve the referenced elements
        resolve_referenced_elements(osm_element)

        if OSMElement.get_conflicting_elements().count() == 0:
            replay_tool = ReplayTool.objects.get()
            replay_tool.state = ReplayTool.STATUS_RESOLVED
            replay_tool.save()
        return Response(OSMElementSerializer(osm_element).data)

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'resolve/(?P<whose>(theirs|ours))',
    )
    def resolve_theirs_or_ours(self, request, whose, pk=None):
        osm_element = self.get_object()
        if whose == 'theirs':
            osm_element.resolved_data = osm_element.upstream_data
        else:
            osm_element.resolved_data = osm_element.local_data
        osm_element.status = OSMElement.STATUS_RESOLVED
        osm_element.save()

        # Resolve the referenced elements

        # Note that while completely resolving theirs/ours, resolved data does not
        # contain the conflicting nodes info, which is looked into by the `resolve_referenced_elements`
        # function. So manually collect the referenced elements and update them
        for elem in osm_element.referenced_elements.all():
            elem.resolved_data = elem.upstream_data if whose == 'theirs' else elem.local_data
            elem.save()
        # resolve_referenced_elements(osm_element)

        if OSMElement.get_conflicting_elements().count() == 0:
            replay_tool = ReplayTool.objects.get()
            replay_tool.state = ReplayTool.STATUS_RESOLVED
            replay_tool.save()
        return Response(OSMElementSerializer(osm_element).data)

    def remove_meta_keys(self, data):
        for key in META_KEYS:
            data.pop(key, None)
        return data

    def validate_and_process_data(self, data, osm_element):
        if osm_element.type == OSMElement.TYPE_NODE:
            data.pop('conflicting_nodes', None)
        else:
            data.pop('location', None)
        data = self.remove_meta_keys(data)
        return data


def update_referenced_elements(osm_element: OSMElement) -> None:
    if osm_element.type == OSMElement.TYPE_NODE:
        return
    nodes = osm_element.resolved_data.get('conflicting_nodes') or {}

    for nid, location_data in nodes.items():
        node = OSMElement.objects.get(element_id=nid, type=OSMElement.TYPE_NODE)
        node.resolved_data['location'] = {
            'lat': location_data['lat'],
            'lon': location_data['lon'],
        }
        node.status = OSMElement.STATUS_PARTIALLY_RESOLVED
        node.save()


def resolve_referenced_elements(osm_element: OSMElement) -> None:
    if osm_element.type == OSMElement.TYPE_NODE:
        return
    nodes = osm_element.resolved_data.get('conflicting_nodes') or {}

    for nid, location_data in nodes.items():
        node = OSMElement.objects.get(element_id=nid, type=OSMElement.TYPE_NODE)
        node.resolved_data['location'] = {
            'lat': location_data['lat'],
            'lon': location_data['lon'],
        }
        node.status = OSMElement.STATUS_RESOLVED
        node.save()
