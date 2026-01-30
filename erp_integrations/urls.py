from django.urls import re_path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ERPConnectionViewSet,
    ERPAPIDefinitionViewSet,
    BuildPayloadView,
    ErpEtlImportView,
)


class LooseSlashRouter(DefaultRouter):
    trailing_slash = r"/?"


router = LooseSlashRouter()
router.register("connections", ERPConnectionViewSet, basename="erp-connection")
router.register("api-definitions", ERPAPIDefinitionViewSet, basename="erp-api-definition")

urlpatterns = [
    re_path(r"api/", include(router.urls)),
    re_path(r"api/build-payload/?", BuildPayloadView.as_view(), name="erp-integrations-build-payload"),
    re_path(r"api/etl-import/?", ErpEtlImportView.as_view(), name="erp-etl-import"),
]
