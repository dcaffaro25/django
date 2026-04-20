"""URL routing for the new report engine.

Mounted by :mod:`accounting.urls` under ``/api/reports/`` (tenant-prefixed by
the root URL conf). The stub endpoints for ``/calculate/``, ``/save/``,
``/export/*``, ``/ai/*`` are registered here from day one so the client surface
is stable; each returns 501 until its PR implements it.
"""

from rest_framework.routers import DefaultRouter

from .views import (
    AiStub,
    CalculateStub,
    ExportStub,
    ReportInstanceViewSet,
    ReportTemplateViewSet,
    SaveStub,
)

router = DefaultRouter()
router.register(r"templates", ReportTemplateViewSet, basename="reports-templates")
router.register(r"instances", ReportInstanceViewSet, basename="reports-instances")
router.register(r"calculate", CalculateStub, basename="reports-calculate")
router.register(r"save", SaveStub, basename="reports-save")
router.register(r"export", ExportStub, basename="reports-export")
router.register(r"ai", AiStub, basename="reports-ai")

urlpatterns = router.urls
