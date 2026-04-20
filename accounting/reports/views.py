"""ViewSets for :mod:`accounting.reports`.

PR 1 scope: CRUD for ``ReportTemplate`` and read + metadata-update for
``ReportInstance``. The stateless ``/calculate/``, ``/save/``, ``/export/*``,
and ``/ai/*`` endpoints land in later PRs; stubs are included here returning
501 so the URL surface is stable from day one.
"""

from copy import deepcopy

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from multitenancy.mixins import ScopedQuerysetMixin

from .models import ReportInstance, ReportTemplate
from .serializers import (
    ReportInstanceListSerializer,
    ReportInstanceSerializer,
    ReportTemplateSerializer,
)


class ReportTemplateViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for report templates (the JSON-document form)."""

    queryset = ReportTemplate.objects.all()
    serializer_class = ReportTemplateSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        report_type = self.request.query_params.get("report_type")
        if report_type:
            qs = qs.filter(report_type=report_type)
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        return qs

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        if not tenant or tenant == "all":
            raise ValidationError("Company/tenant not found in request")
        with transaction.atomic():
            serializer.save(company=tenant)

    def perform_update(self, serializer):
        with transaction.atomic():
            serializer.save()

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None, tenant_id=None):
        """Copy a template, appending ``(Copy)`` to the name."""
        original = self.get_object()
        new_doc = deepcopy(original.document or {})
        copy = ReportTemplate.objects.create(
            company=original.company,
            name=f"{original.name} (Copy)",
            report_type=original.report_type,
            description=original.description,
            document=new_doc,
            is_active=original.is_active,
            is_default=False,
        )
        serializer = self.get_serializer(copy)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def set_default(self, request, pk=None, tenant_id=None):
        """Mark this template as the default for its report type."""
        tpl = self.get_object()
        ReportTemplate.objects.filter(
            company=tpl.company,
            report_type=tpl.report_type,
            is_default=True,
        ).exclude(id=tpl.id).update(is_default=False)
        tpl.is_default = True
        tpl.save(update_fields=["is_default"])
        return Response({"status": "default set"})


class ReportInstanceViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """Read + metadata-update (status, notes) for saved report instances.

    Creation is handled by ``/api/reports/save/`` (see later PR); POST to the
    collection endpoint is disabled.
    """

    queryset = ReportInstance.objects.all()
    serializer_class = ReportInstanceSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return ReportInstanceListSerializer
        return self.serializer_class

    def get_queryset(self):
        qs = super().get_queryset()
        report_type = self.request.query_params.get("report_type")
        if report_type:
            qs = qs.filter(report_type=report_type)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        template = self.request.query_params.get("template")
        if template:
            qs = qs.filter(template_id=template)
        return qs


# --- Stubs for later PRs ----------------------------------------------------
#
# These are registered now so the URL surface is stable and the OpenAPI / API
# discovery is predictable. Each returns HTTP 501 until the corresponding PR
# implements it.

class NotImplementedMixin:
    @staticmethod
    def _not_implemented(feature: str):
        return Response(
            {"error": f"{feature} — not yet implemented (lands in a later PR)"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class CalculateStub(NotImplementedMixin, viewsets.ViewSet):
    def create(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/calculate/")


class SaveStub(NotImplementedMixin, viewsets.ViewSet):
    def create(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/save/")


class ExportStub(NotImplementedMixin, viewsets.ViewSet):
    @action(detail=False, methods=["post"], url_path="xlsx")
    def xlsx(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/export/xlsx/")

    @action(detail=False, methods=["post"], url_path="pdf")
    def pdf(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/export/pdf/")


class AiStub(NotImplementedMixin, viewsets.ViewSet):
    @action(detail=False, methods=["post"], url_path="generate-template")
    def generate_template(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/ai/generate-template/")

    @action(detail=False, methods=["post"])
    def refine(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/ai/refine/")

    @action(detail=False, methods=["post"])
    def chat(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/ai/chat/")

    @action(detail=False, methods=["post"])
    def explain(self, request, tenant_id=None):
        return self._not_implemented("POST /api/reports/ai/explain/")
