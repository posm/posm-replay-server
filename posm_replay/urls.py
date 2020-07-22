"""posm_replay URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from rest_framework import routers

from replay_tool.views import (
    ReplayToolView,
    ConflictsViewSet,
    trigger,
    retrigger,
    reset,
    LoginPageView,
    ResolvedElementsView,
    UnresolvedElementsView,
    PartialResolvedElementsView,
    ReplayToolConfigViewset,
    AllChangesViewset,
)


router = routers.DefaultRouter()

router.register('conflicts', ConflictsViewSet, basename='conflicts')
router.register('resolved-elements', ResolvedElementsView, basename='resolved-elements')
router.register('unresolved-elements', UnresolvedElementsView, basename='unresolved-elements')
router.register('partial-resolved-elements', PartialResolvedElementsView, basename='partial-resolved-elements')
router.register('config', ReplayToolConfigViewset, basename='config')
router.register('all-changes', AllChangesViewset, basename='all-changes')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/replay-tool/', ReplayToolView.as_view()),
    path('api/v1/trigger/', trigger),
    path('api/v1/reset/', reset),
    path('api/v1/re-trigger/', retrigger),
    path('api/v1/', include(router.urls)),
    path('login/', LoginPageView.as_view()),
    path('', include('social_django.urls', namespace='social')),
]
