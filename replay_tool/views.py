from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework import viewsets, exceptions
from rest_framework.response import Response

from django.db import transaction, models

from django.views.generic.base import TemplateView

from social_django.utils import psa


from .tasks import task_prepare_data_for_replay_tool

from .models import ReplayTool, OSMElement, ReplayToolConfig, LocalChangeSet
from .serializers.models import (
    ReplayToolSerializer,
    OSMElementSerializer,
    MiniOSMElementSerializer,
    ReplayToolConfigSerializer,
)

META_KEYS = [
    'id', 'uid', 'user', 'version', 'changeset', 'timestamp',
]


class ReplayToolView(APIView):
    def get(self, request, version=None, format=None):
        tool, _ = ReplayTool.objects.get_or_create(defaults={'is_current_state_complete': True})
        return Response(ReplayToolSerializer(tool).data)


@api_view(['POST'])
def trigger(request):
    tool = ReplayTool.objects.get()
    if not tool.is_initiated:
        task_prepare_data_for_replay_tool.delay()
        return Response({'message': 'ReplayTool has been successfully triggered.'})
    raise exceptions.ValidationError('Already triggered.')


@api_view(['POST'])
def retrigger_all(request):
    ReplayTool.reset()
    task_prepare_data_for_replay_tool.delay()
    return Response({'message': 'Replay Tool has been successfully re-triggered.'})


@api_view(['POST'])
def reset(request):
    ReplayTool.reset()
    task_prepare_data_for_replay_tool.delay()
    return Response({'message': 'Replay Tool has been successfully reset.'})


@api_view(['POST'])
def retrigger(request):
    replay_tool = ReplayTool.objects.get()
    RT = ReplayTool
    if replay_tool.state == RT.STATUS_GATHERING_CHANGESETS:
        LocalChangeSet.objects.all().delete()
        replay_tool.state = RT.STATUS_NOT_TRIGGERRED
    elif replay_tool.state == RT.STATUS_EXTRACTING_UPSTREAM_AOI:
        # Nothing extra to be done, just creates files, which will be overridden
        replay_tool.state = RT.STATUS_GATHERING_CHANGESETS
    elif replay_tool.state == RT.STATUS_EXTRACTING_LOCAL_AOI:
        # Nothing extra to be done, just creates files, which will be overridden
        replay_tool.state = RT.STATUS_EXTRACTING_UPSTREAM_AOI
    elif replay_tool.state == RT.STATUS_DETECTING_CONFLICTS:
        replay_tool.state = RT.STATUS_EXTRACTING_LOCAL_AOI
        OSMElement.objects.all().delete()
    elif replay_tool.state == RT.STATUS_CREATING_GEOJSONS:
        replay_tool.state = RT.STATUS_DETECTING_CONFLICTS
        # Do nothing, re-generating geojsons will override the contents
    elif replay_tool.state == RT.STATUS_RESOLVING_CONFLICTS:
        replay_tool.state = RT.STATUS_EXTRACTING_UPSTREAM_AOI
        OSMElement.objects.all().delete()
    elif replay_tool.state == RT.STATUS_PUSH_CONFLICTS:
        replay_tool.state = RT.STATUS_NOT_TRIGGERRED
        # Remove changesets
        LocalChangeSet.objects.all().delete()
        # Don't remove the OSMElements, they will be reused

    replay_tool.has_errored = False
    replay_tool.error_details = ""
    replay_tool.is_current_state_complete = True
    replay_tool.save()
    task_prepare_data_for_replay_tool.delay(replay_tool.state)
    return Response({'message': 'Replay Tool has been successfully re-triggered.'})


@psa('social:complete')
def push_upstream(request):
    # NOTE: After returning from this function, user_data() of the backend(openstreetmap backend)
    #  will be called which will in turn call create_and_push_changeset() method inside a thread
    pass


class AllChangesViewset(viewsets.ReadOnlyModelViewSet):
    serializer_class = OSMElementSerializer

    def get_queryset(self, *args, **kwrags):
        queryset = OSMElement.objects.all()
        if self.request.query_params.get('state') == 'no-conflicts':
            # Return only non conflicting elements
            return queryset.filter(
                ~models.Q(local_state=OSMElement.LOCAL_STATE_CONFLICTING),
            )
        else:
            return queryset


class ConflictsViewSet(viewsets.ModelViewSet):
    queryset = OSMElement.get_all_conflicting_elements()

    def get_serializer_class(self):
        if self.action == 'list':
            return MiniOSMElementSerializer
        return OSMElementSerializer

    @action(
        detail=False,
        methods=['get'],
        url_path=r'all',
    )
    def all_elements(self, request):
        queryset = OSMElement.get_all_local_elements()
        self.page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(self.page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(
        detail=True,
        methods=['put'],
        url_path='reset',
    )
    def reset_element(self, request, pk=None):
        osm_element = self.get_object()

        osm_element.resolved_data = {}
        osm_element.status = OSMElement.STATUS_UNRESOLVED
        osm_element.resolved_from = None
        osm_element.save()

        # Change state of replay tool to conflict, just in case it has been resolved
        replay_tool = ReplayTool.objects.get()
        replay_tool.state = ReplayTool.STATUS_RESOLVING_CONFLICTS
        replay_tool.is_current_state_complete = False
        replay_tool.save()

        # Update the referenced elements
        reset_referenced_elements(osm_element)

        return Response(OSMElementSerializer(osm_element).data)

    @action(
        detail=True,
        methods=['patch'],
        url_path=r'update',
    )
    def update_element(self, request, pk=None):
        osm_element = self.get_object()
        data = self.validate_and_process_data(request.data, osm_element)

        osm_element.resolved_data = {
            **data,
            'id': osm_element.element_id
        }
        osm_element.status = OSMElement.STATUS_PARTIALLY_RESOLVED
        osm_element.save()
        # Update replay tool, in case resolving_conflicts state has been marked complete
        replay_tool = ReplayTool.objects.get()
        replay_tool.state = ReplayTool.STATUS_RESOLVING_CONFLICTS
        replay_tool.is_current_state_complete = False
        replay_tool.save()

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

        osm_element.resolved_data = {
            **data,
            'id': osm_element.element_id
        }
        osm_element.status = OSMElement.STATUS_RESOLVED
        osm_element.resolved_from = OSMElement.RESOLVED_FROM_CUSTOM
        osm_element.save()
        # Resolve the referenced elements
        resolve_referenced_elements(osm_element)

        if OSMElement.get_conflicting_elements().count() == 0:
            replay_tool = ReplayTool.objects.get()
            replay_tool.is_current_state_complete = True
            replay_tool.save()
        return Response(OSMElementSerializer(osm_element).data)

    @action(
        detail=True,
        methods=['put'],
        url_path=r'resolve/(?P<whose>(theirs|ours))',
    )
    def resolve_theirs_or_ours(self, request, whose, pk=None):
        osm_element = self.get_object()
        if whose == 'theirs':
            osm_element.resolved_data = osm_element.upstream_data
        else:
            osm_element.resolved_data = osm_element.local_data
        osm_element.status = OSMElement.STATUS_RESOLVED
        osm_element.resolved_from = whose
        osm_element.save()

        # Resolve the referenced elements

        # Note that while completely resolving theirs/ours, resolved data does not
        # contain the conflicting nodes info, which is looked into by the `resolve_referenced_elements`
        # function. So manually collect the referenced elements and update them
        for elem in osm_element.referenced_elements.all():
            elem.resolved_data = elem.upstream_data if whose == 'theirs' else elem.local_data
            elem.resolved_from = whose
            elem.save()
        # resolve_referenced_elements(osm_element)

        if OSMElement.get_conflicting_elements().count() == 0:
            replay_tool = ReplayTool.objects.get()
            replay_tool.is_current_state_complete = True
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


@transaction.atomic
def reset_referenced_elements(osm_element: OSMElement) -> None:
    if osm_element.type == OSMElement.TYPE_NODE:
        return
    nodes = osm_element.resolved_data.get('conflicting_nodes') or {}

    for nid, location_data in nodes.items():
        node = OSMElement.objects.get(element_id=nid, type=OSMElement.TYPE_NODE)
        node.resolved_data = {}
        node.status = OSMElement.STATUS_UNRESOLVED
        node.resolved_from = None
        node.save()


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
        node.resolved_from = OSMElement.RESOLVED_FROM_CUSTOM
        node.save()


class ReplayToolConfigViewset(viewsets.ModelViewSet):
    def __init__(self, *args, **kwargs):
        ReplayToolConfig.load()
        super().__init__(*args, **kwargs)

    queryset = ReplayToolConfig.objects.all()
    serializer_class = ReplayToolConfigSerializer


class LoginPageView(TemplateView):
    template_name = "login.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class ResolvedElementsView(viewsets.ReadOnlyModelViewSet):
    queryset = OSMElement.get_resolved_elements()
    serializer_class = OSMElementSerializer


class UnresolvedElementsView(viewsets.ReadOnlyModelViewSet):
    queryset = OSMElement.get_conflicting_elements()
    serializer_class = OSMElementSerializer


class PartialResolvedElementsView(viewsets.ReadOnlyModelViewSet):
    queryset = OSMElement.get_partially_resolved_elements()
    serializer_class = OSMElementSerializer
