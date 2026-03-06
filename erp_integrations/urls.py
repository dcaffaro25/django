from django.urls import re_path, include
from rest_framework.routers import DefaultRouter

from .views import (
    ERPConnectionViewSet,
    ERPAPIDefinitionViewSet,
    ERPRawRecordViewSet,
    ERPSyncJobViewSet,
    ERPSyncRunViewSet,
    BuildPayloadView,
    ErpEtlImportView,
)


class LooseSlashRouter(DefaultRouter):
    trailing_slash = r"/?"


router = LooseSlashRouter()
router.register("connections", ERPConnectionViewSet, basename="erp-connection")
router.register("api-definitions", ERPAPIDefinitionViewSet, basename="erp-api-definition")
router.register("sync-jobs", ERPSyncJobViewSet, basename="erp-sync-job")
router.register("sync-runs", ERPSyncRunViewSet, basename="erp-sync-run")
router.register("raw-records", ERPRawRecordViewSet, basename="erp-raw-record")

urlpatterns = [
    re_path(r"api/", include(router.urls)),
    re_path(r"api/build-payload/?", BuildPayloadView.as_view(), name="erp-integrations-build-payload"),
    re_path(r"api/etl-import/?", ErpEtlImportView.as_view(), name="erp-etl-import"),
]
