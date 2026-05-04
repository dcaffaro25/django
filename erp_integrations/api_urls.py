"""
ERP integration routes relative to /<tenant>/api/ (no leading api/ segment).

Mounted from accounting/urls.py together with the accounting API router so
paths like /{tenant}/api/sync-jobs/ resolve (see nord_backend URL order).
"""

from django.urls import include, path, re_path
from rest_framework.routers import DefaultRouter

from .views import (
    ERPAPIDefinitionViewSet,
    ERPConnectionViewSet,
    ERPRawRecordViewSet,
    ERPSyncJobViewSet,
    ERPSyncPipelineRunViewSet,
    ERPSyncPipelineViewSet,
    ERPSyncRunViewSet,
    BuildPayloadView,
    ErpEtlImportView,
    PedidoVendasReportView,
    PipelineSandboxView,
)


class LooseSlashRouter(DefaultRouter):
    trailing_slash = r"/?"


router = LooseSlashRouter()
router.register("connections", ERPConnectionViewSet, basename="erp-connection")
router.register("api-definitions", ERPAPIDefinitionViewSet, basename="erp-api-definition")
router.register("sync-jobs", ERPSyncJobViewSet, basename="erp-sync-job")
router.register("sync-runs", ERPSyncRunViewSet, basename="erp-sync-run")
router.register("raw-records", ERPRawRecordViewSet, basename="erp-raw-record")
router.register("sync-pipelines", ERPSyncPipelineViewSet, basename="erp-sync-pipeline")
router.register("pipeline-runs", ERPSyncPipelineRunViewSet, basename="erp-pipeline-run")

urlpatterns = [
    path("", include(router.urls)),
    re_path(r"^build-payload/?$", BuildPayloadView.as_view(), name="erp-integrations-build-payload"),
    re_path(r"^etl-import/?$", ErpEtlImportView.as_view(), name="erp-etl-import"),
    re_path(r"^pipeline-sandbox/?$", PipelineSandboxView.as_view(), name="erp-pipeline-sandbox"),
    re_path(
        r"^erp/reports/pedidos/?$",
        PedidoVendasReportView.as_view(),
        name="erp-pedidos-report",
    ),
]
