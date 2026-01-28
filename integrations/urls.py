from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ERPConnectionViewSet,
    ERPAPIDefinitionViewSet,
    BuildPayloadView,
)


class LooseSlashRouter(DefaultRouter):
    trailing_slash = r"/?"


router = LooseSlashRouter()
router.register("connections", ERPConnectionViewSet, basename="erp-connection")
router.register("api-definitions", ERPAPIDefinitionViewSet, basename="erp-api-definition")

urlpatterns = [
    re_path(r"api/", include(router.urls)),
    re_path(r"api/build-payload/?", BuildPayloadView.as_view(), name="integrations-build-payload"),
]
