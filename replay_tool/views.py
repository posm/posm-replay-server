from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from replay_tool.utils.common import (
    get_current_aoi_bbox, get_aoi_name,
    get_aoi_created_datetime,
)

from .models import LocalChangeSet, ReplayTool
from .serializers import ReplayToolSerializer


class ReplayToolViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ReplayToolSerializer
    queryset = ReplayTool.objects.all()


class CurrentAOIView(APIView):
    def get(self, request, version=None, format=None):
        aoi = {
            'name': get_aoi_name(exception_if_not_set=True),
            'bounds': get_current_aoi_bbox(),
            'date_cloned': get_aoi_created_datetime(),
            'local_changesets_count': LocalChangeSet.objects.count(),
        }
        return Response(aoi)
