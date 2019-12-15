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
from django.urls import path
from django.urls import path, include

from rest_framework import routers

from replay_tool.views import (
    CurrentAOIView,
    ReplayToolViewSet,
    ConflictsView,
)


router = routers.DefaultRouter()

router.register(r'replay-tool', ReplayToolViewSet, basename='replay_tool')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/current-aoi/', CurrentAOIView.as_view()),
    path('api/v1/conflicts/', ConflictsView.as_view()),
    path('api/v1/', include(router.urls)),
]
