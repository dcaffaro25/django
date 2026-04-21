"""ViewSets for :mod:`accounting.reports`.

PR 3: the stateless /calculate/, /save/, /export/{xlsx,pdf}/ endpoints now
sit on the real ``ReportCalculator`` + exporters. AI endpoints remain stubs
pending PR 6+.
"""

from copy import deepcopy

from django.db import transaction
from django.http import HttpResponse
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
from .services.ai_assistant import (
    AiAssistantError,
    chat as ai_chat,
    explain as ai_explain,
    generate_template,
    refine_template,
    summarize_changes,
)
from .services.calculator import ReportCalculator
from .services.document_schema import validate_document
from .services.exporter_pdf import PdfBackendUnavailable, build_pdf
from .services.exporter_xlsx import build_xlsx


# --- Template CRUD ---------------------------------------------------------


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
        tenant = _tenant_or_raise(self.request)
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
        tpl = self.get_object()
        ReportTemplate.objects.filter(
            company=tpl.company,
            report_type=tpl.report_type,
            is_default=True,
        ).exclude(id=tpl.id).update(is_default=False)
        tpl.is_default = True
        tpl.save(update_fields=["is_default"])
        return Response({"status": "default set"})


# --- Instances CRUD (metadata only) ---------------------------------------


class ReportInstanceViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """Read + metadata-update (status, notes) for saved report instances.

    Creation goes through ``/api/reports/save/`` (see :class:`SaveViewSet`).
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
        rt = self.request.query_params.get("report_type")
        if rt:
            qs = qs.filter(report_type=rt)
        status_q = self.request.query_params.get("status")
        if status_q:
            qs = qs.filter(status=status_q)
        tpl = self.request.query_params.get("template")
        if tpl:
            qs = qs.filter(template_id=tpl)
        return qs


# --- Stateless: Calculate -------------------------------------------------


class CalculateViewSet(viewsets.ViewSet):
    """``POST /api/reports/calculate/`` — runs ``ReportCalculator`` and returns
    the result. Accepts either an inline ``template`` (the canonical JSON
    document) or a saved ``template_id``. Never writes to the DB.
    """

    def create(self, request, tenant_id=None):
        tenant = _tenant_or_raise(request)
        body = request.data or {}

        document = _resolve_inline_or_id(body, company=tenant)
        periods = body.get("periods") or []
        options = body.get("options") or {}
        if not isinstance(periods, list) or not periods:
            raise ValidationError({"periods": "At least one period is required"})

        calc = ReportCalculator(company_id=tenant.id)
        try:
            result = calc.calculate(document=document, periods=periods, options=options)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result, status=status.HTTP_200_OK)


# --- Stateful: Save -------------------------------------------------------


class SaveViewSet(viewsets.ViewSet):
    """``POST /api/reports/save/`` — persists a ``ReportInstance``.

    Accepts either ``{template_id, periods, options, name, status, notes}``
    (the server runs /calculate/ internally and saves the result) or
    ``{template, periods, options, result, name, status, notes}`` (the client
    already has the result and just wants to save it). Supplying ``result``
    avoids re-running the calculation; the server still re-validates the
    document for the template_snapshot copy.
    """

    def create(self, request, tenant_id=None):
        tenant = _tenant_or_raise(request)
        body = request.data or {}

        name = (body.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Name is required"})

        document = _resolve_inline_or_id(body, company=tenant)
        periods = body.get("periods") or []
        options = body.get("options") or {}
        result = body.get("result")
        state = body.get("status", "draft")

        if not isinstance(periods, list) or not periods:
            raise ValidationError({"periods": "At least one period is required"})

        # Either recompute or trust what the client sends. Recomputing is
        # cheaper than the round-trip of /calculate/ + /save/ for most cases,
        # so default to recomputing unless the client explicitly passed a
        # result payload.
        if not result:
            calc = ReportCalculator(company_id=tenant.id)
            try:
                result = calc.calculate(document=document, periods=periods, options=options)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc

        template_id = body.get("template_id")
        template_obj = None
        if template_id:
            try:
                template_obj = ReportTemplate.objects.get(id=template_id, company=tenant)
            except ReportTemplate.DoesNotExist:
                pass  # soft reference; we snapshot the document regardless

        with transaction.atomic():
            instance = ReportInstance.objects.create(
                company=tenant,
                template=template_obj,
                template_snapshot=_coerce_to_dict(document),
                name=name,
                report_type=_coerce_to_dict(document).get("report_type", "custom"),
                periods=result.get("periods", periods),
                result=result,
                status=state,
                generated_by=request.user if getattr(request.user, "is_authenticated", False) else None,
                notes=body.get("notes"),
            )

        serializer = ReportInstanceSerializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# --- Export: XLSX & PDF ---------------------------------------------------


class ExportViewSet(viewsets.ViewSet):
    """``POST /api/reports/export/{xlsx,pdf}/``.

    Body: either ``{result, name?}`` (stateless — render what the client
    already has) or ``{instance_id}`` (load the persisted result and render).
    Both variants return the binary directly with the right content-type and
    Content-Disposition so the browser downloads.
    """

    @action(detail=False, methods=["post"], url_path="xlsx")
    def xlsx(self, request, tenant_id=None):
        tenant = _tenant_or_raise(request)
        result, name = _load_result(request.data or {}, tenant=tenant)
        blob = build_xlsx(result, name=name)
        resp = HttpResponse(
            blob,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{_safe_filename(name)}.xlsx"'
        return resp

    @action(detail=False, methods=["post"], url_path="pdf")
    def pdf(self, request, tenant_id=None):
        tenant = _tenant_or_raise(request)
        result, name = _load_result(request.data or {}, tenant=tenant)
        try:
            blob = build_pdf(result, name=name)
        except PdfBackendUnavailable as exc:
            return Response(
                {"error": str(exc)}, status=status.HTTP_501_NOT_IMPLEMENTED,
            )
        resp = HttpResponse(blob, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{_safe_filename(name)}.pdf"'
        return resp


# --- AI Stubs (implemented in later PRs) ----------------------------------


class AiStub(viewsets.ViewSet):
    """AI endpoints. ``generate-template`` is live (PR 6); the rest land in
    later PRs and return 501 with a helpful message until then.
    """

    @staticmethod
    def _ni(feature: str):
        return Response(
            {"error": f"{feature} — not yet implemented (lands in a later PR)"},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )

    @action(detail=False, methods=["post"], url_path="generate-template")
    def generate_template(self, request, tenant_id=None):
        """Generate a draft template from the tenant's chart of accounts.

        Body::

            {
              "report_type": "income_statement" | "balance_sheet" | "cash_flow",
              "preferences": "optional free-text",
              "provider": "openai" | "anthropic" (optional),
              "model": "..." (optional)
            }

        Returns the draft ``TemplateDocument`` (JSON). Never persists.
        """
        tenant = _tenant_or_raise(request)
        body = request.data or {}

        report_type = (body.get("report_type") or "").strip()
        if report_type not in ("income_statement", "balance_sheet", "cash_flow"):
            raise ValidationError(
                {"report_type": "Must be income_statement | balance_sheet | cash_flow"}
            )

        try:
            doc = generate_template(
                company_id=tenant.id,
                report_type=report_type,
                preferences=(body.get("preferences") or ""),
                provider=body.get("provider"),
                model=body.get("model"),
            )
        except AiAssistantError as exc:
            # Service layer signals any upstream AI failure (missing key,
            # malformed output, schema violation after repair) as this
            # exception. Render a 502-ish via a structured 400 so the UI can
            # surface the message.
            return Response(
                {"error": str(exc), "error_type": "ai_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"document": doc}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def refine(self, request, tenant_id=None):
        """Apply a one-shot refine action to an existing template.

        Body::

            {
              "action": "normalize_labels" | "translate_en" | "translate_pt"
                        | "suggest_subtotals" | "add_missing_accounts",
              "document": { ... full template document ... },
              "provider": "openai" | "anthropic" (optional),
              "model": "..." (optional)
            }

        Response::

            {
              "document": <refined document>,
              "summary": { added_ids, removed_ids, renamed, old_count, new_count }
            }

        The client is expected to diff and preview before applying.
        """
        tenant = _tenant_or_raise(request)
        body = request.data or {}
        action_name = (body.get("action") or "").strip()
        document = body.get("document")
        if not isinstance(document, dict):
            raise ValidationError({"document": "Provide the current template document"})
        if not action_name:
            raise ValidationError({"action": "Provide a refine action"})

        try:
            new_doc = refine_template(
                company_id=tenant.id,
                document=document,
                action=action_name,
                provider=body.get("provider"),
                model=body.get("model"),
            )
        except AiAssistantError as exc:
            return Response(
                {"error": str(exc), "error_type": "ai_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        summary = summarize_changes(document, new_doc)
        return Response({"document": new_doc, "summary": summary}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def chat(self, request, tenant_id=None):
        """Conversational assistant with tool-calling operations.

        Body::

            {
              "messages": [{"role": "user"|"assistant", "content": "..."}, ...],
              "document": { ...current template... },
              "preview_result": { ...optional /calculate/ result... },
              "provider": "openai"|"anthropic" (optional),
              "model": "..." (optional)
            }

        Returns::

            {
              "assistant_message": "human reply in pt-BR",
              "operations": [ {op: "add_block"|"update_block"|..., ...}, ... ]
            }

        Operations are proposed changes — the UI renders each as a diff
        card and applies only the ones the user accepts. Non-streaming in
        this PR; SSE streaming is a later polish.
        """
        _tenant_or_raise(request)
        body = request.data or {}

        messages = body.get("messages")
        document = body.get("document")
        if not isinstance(messages, list) or not messages:
            raise ValidationError({"messages": "Provide at least one message"})
        if not isinstance(document, dict):
            raise ValidationError({"document": "Provide the current template document"})

        try:
            result = ai_chat(
                messages=messages,
                document=document,
                preview_result=body.get("preview_result"),
                provider=body.get("provider"),
                model=body.get("model"),
            )
        except AiAssistantError as exc:
            return Response(
                {"error": str(exc), "error_type": "ai_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"])
    def explain(self, request, tenant_id=None):
        """Explain a single cell in the preview result.

        Body::

            {
              "document": {...},
              "result":   {...},  // /calculate/ response
              "block_id": "revenue_gross",
              "period_id": "cur",
              "provider": "openai"|"anthropic" (optional),
              "model":    "..."  (optional)
            }

        Returns::

            {
              "text": "Explicação em pt-BR ...",
              "block_id": "...",
              "period_id": "...",
              "value": <number|null>,
              "accounts": [{id, account_code, name, path}, ...]
            }

        Falls back to a coded (non-AI) explanation if the AI call fails —
        the UI still gets something useful, just less conversational.
        """
        tenant = _tenant_or_raise(request)
        body = request.data or {}

        document = body.get("document")
        result = body.get("result")
        block_id = body.get("block_id")
        period_id = body.get("period_id")

        if not isinstance(document, dict):
            raise ValidationError({"document": "Provide the template document"})
        if not isinstance(result, dict):
            raise ValidationError({"result": "Provide a /calculate/ result"})
        if not block_id or not period_id:
            raise ValidationError({"block_id": "block_id and period_id required"})

        try:
            payload = ai_explain(
                company_id=tenant.id,
                document=document,
                result=result,
                block_id=block_id,
                period_id=period_id,
                provider=body.get("provider"),
                model=body.get("model"),
            )
        except AiAssistantError as exc:
            return Response(
                {"error": str(exc), "error_type": "ai_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(payload, status=status.HTTP_200_OK)


# --- Helpers --------------------------------------------------------------


def _tenant_or_raise(request):
    tenant = getattr(request, "tenant", None)
    if not tenant or tenant == "all":
        raise ValidationError("Company/tenant not found in request")
    return tenant


def _resolve_inline_or_id(body: dict, company) -> dict:
    """Return the document dict for either ``{template: {...}}`` or
    ``{template_id: N}``. Inline wins if both are present.
    """
    inline = body.get("template") or body.get("document")
    if inline:
        # Validate now so /calculate/ gets a clean 400 instead of a cryptic
        # exception from deeper in the stack.
        try:
            validate_document(inline)
        except Exception as exc:
            raise ValidationError({"template": str(exc)}) from exc
        return inline

    template_id = body.get("template_id")
    if not template_id:
        raise ValidationError(
            {"template": "Provide either 'template' (inline) or 'template_id'"},
        )
    try:
        tpl = ReportTemplate.objects.get(id=template_id, company=company)
    except ReportTemplate.DoesNotExist:
        raise ValidationError({"template_id": f"No template with id {template_id}"})
    return tpl.document


def _load_result(body: dict, tenant) -> tuple[dict, str]:
    """Extract a result + name from either an inline result or an instance_id."""
    if body.get("instance_id"):
        try:
            inst = ReportInstance.objects.get(id=body["instance_id"], company=tenant)
        except ReportInstance.DoesNotExist:
            raise ValidationError({"instance_id": "Not found"})
        return inst.result, inst.name

    result = body.get("result")
    name = body.get("name") or "Demonstrativo"
    if not isinstance(result, dict) or "lines" not in result:
        raise ValidationError(
            {"result": "Provide either 'instance_id' or a result dict with 'lines'"},
        )
    return result, name


def _coerce_to_dict(doc) -> dict:
    """Accept either a dict (inline) or a pydantic model (unlikely here)."""
    if hasattr(doc, "model_dump"):
        return doc.model_dump(mode="json")
    return doc


def _safe_filename(name: str) -> str:
    return "".join(c for c in (name or "report") if c.isalnum() or c in "-_ ").strip() or "report"
