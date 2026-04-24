"""DRF views for the v2 template-import flow.

Endpoints mounted at ``/api/core/imports/v2/...``:

  * ``POST /analyze``            — upload file, enqueue analyze.
  * ``POST /resolve/<id>``       — apply resolutions, re-detect issues.
  * ``POST /commit/<id>``        — enqueue commit for a ready session.
  * ``GET /sessions/<id>``       — fetch session state (used for polling).
  * ``DELETE /sessions/<id>``    — discard.

Analyze and commit both return 202 Accepted (not 201/200): the heavy
work runs in a Celery worker (Phase 6.z) and the frontend polls the
detail endpoint until the session leaves its non-terminal status. In
eager mode (dev / tests without ``REDIS_URL``) the worker runs inline
so the returned session is already terminal, and tests that assert
``status in {"ready", "awaiting_resolve", "committed", ...}``
immediately after the response continue to work.

All endpoints are tenant-scoped: the session's ``company_id`` must
match the request's resolved tenant. Cross-tenant access returns 404
(not 403 — we don't want to leak existence).
"""
from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.models import ImportSession
from multitenancy.views import _resolve_bulk_import_company_id

from . import services
from .resolve_handlers import ResolutionError
from .serializers import ImportSessionListSerializer, ImportSessionSerializer


def _perms():
    """Permissions: ``IsAuthenticated`` unless ``AUTH_OFF`` is set globally.

    Mirrors the legacy bulk-import permission policy so v2 can't
    accidentally become more open than v1.
    """
    if getattr(settings, "AUTH_OFF", False):
        return []
    return [permissions.IsAuthenticated()]


def _get_session_or_404(pk: int, company_id: Optional[int]) -> ImportSession:
    """Return the session IF its company matches. 404 on mismatch — we
    treat cross-tenant IDs as non-existent."""
    qs = ImportSession.objects.all()
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    return get_object_or_404(qs, pk=pk)


class AnalyzeTemplateImportView(APIView):
    """``POST /api/core/imports/v2/analyze``

    Multipart form data:
      * ``file``       — XLSX upload (required).
      * ``company_id`` — optional, falls back to user's membership.
      * ``erp_duplicate_behavior`` — "update" (default) / "skip" / "error".

    Returns 201 with the serialized session. ``status`` on the session
    tells the client what to do next — ``ready`` means commit
    immediately; ``awaiting_resolve`` means show the diagnostics panel;
    ``error`` means the file couldn't be parsed.
    """

    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        return _perms()

    def post(self, request, tenant_id: Optional[int] = None, *args, **kwargs) -> Response:
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "missing file"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ``_resolve_bulk_import_company_id`` returns ``(company_id, err_response)``;
        # if err_response is set we bubble it up unchanged so the v2 error
        # shape stays consistent with the legacy endpoint.
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        if not company_id:
            return Response(
                {"error": "could not resolve company"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = file.read()
        if not file_bytes:
            return Response(
                {"error": "uploaded file is empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Config knobs the analyze step honours. Keep narrow for Phase 2;
        # resolve-time options land in Phase 4 as the resolve payload's
        # own schema.
        config = {
            "erp_duplicate_behavior": (
                request.POST.get("erp_duplicate_behavior") or "update"
            ).lower(),
        }

        session = services.analyze_template_async(
            company_id=company_id,
            user=request.user,
            file_bytes=file_bytes,
            file_name=file.name or "upload.xlsx",
            config=config,
        )
        # 202 Accepted — the worker may still be running when this
        # returns (in production). Frontend polls GET /sessions/<id>/
        # until ``status`` leaves ``analyzing``.
        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_202_ACCEPTED,
        )


class AnalyzeETLImportView(APIView):
    """``POST /api/core/etl/v2/analyze/``

    Multipart form data:
      * ``file``                      — XLSX upload (required).
      * ``transformation_rule_id``    — int (required for v2 ETL).
      * ``company_id``                — optional, falls back to user's membership.
      * ``row_limit``                 — int; ``0`` or omitted = all rows.

    Delegates to ``services.analyze_etl`` which re-uses
    ``ETLPipelineService`` with ``commit=False`` under the hood, then
    layers on v2 issue detection (erp_id conflicts in Transactions +
    missing auto-JE parameters). Returns the serialised session.
    """

    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        return _perms()

    def post(self, request, tenant_id: Optional[int] = None, *args, **kwargs) -> Response:
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "missing file"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        if not company_id:
            return Response(
                {"error": "could not resolve company"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rule_id_raw = request.POST.get("transformation_rule_id")
        if not rule_id_raw:
            return Response(
                {"error": "transformation_rule_id is required for ETL v2 analyze"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            rule_id = int(rule_id_raw)
        except (TypeError, ValueError):
            return Response(
                {"error": "transformation_rule_id must be an integer"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_bytes = file.read()
        if not file_bytes:
            return Response(
                {"error": "uploaded file is empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # row_limit knob mirrors the legacy ETL endpoint. ``0`` = all.
        row_limit_raw = request.POST.get("row_limit")
        config: dict = {}
        if row_limit_raw not in (None, ""):
            try:
                config["row_limit"] = int(row_limit_raw)
            except (TypeError, ValueError):
                return Response(
                    {"error": "row_limit must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # auto_create_journal_entries config. Matches legacy ETL
        # semantics — config lives in the POST body, not on the rule.
        # Accept either a JSON string or a pre-parsed dict (DRF gives
        # us a dict when content-type is multipart with JSON fields;
        # a string otherwise).
        auto_je_raw = request.data.get("auto_create_journal_entries")
        if auto_je_raw:
            if isinstance(auto_je_raw, str):
                import json as _json
                try:
                    config["auto_create_journal_entries"] = _json.loads(auto_je_raw)
                except _json.JSONDecodeError:
                    return Response(
                        {"error": "auto_create_journal_entries must be valid JSON"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif isinstance(auto_je_raw, dict):
                config["auto_create_journal_entries"] = auto_je_raw

        session = services.analyze_etl_async(
            company_id=company_id,
            user=request.user,
            file_bytes=file_bytes,
            file_name=file.name or "upload.xlsx",
            transformation_rule_id=rule_id,
            config=config,
        )
        # 202 Accepted — see AnalyzeTemplateImportView.post for the
        # polling contract.
        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_202_ACCEPTED,
        )


class ImportSessionDetailView(APIView):
    """``GET /api/core/imports/v2/sessions/<id>`` — fetch session state.
    ``DELETE /api/core/imports/v2/sessions/<id>`` — discard."""

    def get_permissions(self):
        return _perms()

    def get(self, request, pk: int, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        session = _get_session_or_404(pk, company_id)
        return Response(ImportSessionSerializer(session).data)

    def delete(self, request, pk: int, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        session = _get_session_or_404(pk, company_id)
        services.discard_session(session)
        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )


class ResolveSessionView(APIView):
    """``POST /api/core/imports/v2/resolve/<pk>/``
    (and the ``/api/core/etl/v2/resolve/<pk>/`` mirror).

    Body:

        {
          "resolutions": [
            {"issue_id": "iss-abc123", "action": "pick_row",
             "params": {"row_id": "R1"}},
            ...
          ]
        }

    Returns the updated session. ``status`` tells the client what to do
    next: ``ready`` → commit; ``awaiting_resolve`` → more issues remain;
    ``error`` → operator aborted.
    """

    def get_permissions(self):
        return _perms()

    def post(self, request, pk: int, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        session = _get_session_or_404(pk, company_id)

        body = request.data if isinstance(request.data, dict) else {}
        resolutions = body.get("resolutions")
        if resolutions is None:
            return Response(
                {"error": "missing `resolutions` array"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(resolutions, list):
            return Response(
                {"error": "`resolutions` must be an array"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = services.resolve_session(session, resolutions)
        except services.ResolveNotApplicable as exc:
            return Response(
                {"error": str(exc), "status": session.status},
                status=status.HTTP_409_CONFLICT,
            )
        except ResolutionError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )


class CommitSessionView(APIView):
    """``POST /api/core/imports/v2/commit/<id>``

    Commits a session whose ``status == ready``. Returns 409 if the
    session still has blocking issues — the operator must resolve them
    first (Phase 4).

    Any write error rolls back the whole commit (inner atomic block) and
    the session moves to ``error``, with a diagnostic in ``result``.
    """

    def get_permissions(self):
        return _perms()

    def post(self, request, pk: int, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err
        session = _get_session_or_404(pk, company_id)

        try:
            session = services.commit_session_async(session)
        except services.CommitNotReady as exc:
            return Response(
                {
                    "error": str(exc),
                    "status": session.status,
                    "hint": (
                        "Resolve open issues first (POST /resolve/<id>) or "
                        "check the session status via GET."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 202 Accepted — the worker may still be running when this
        # returns (in production). In eager mode the worker ran inline,
        # so the returned session is already ``committed`` or ``error``.
        # Either way, frontend polls GET /sessions/<id>/ for status.
        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_202_ACCEPTED,
        )


class _ImportSessionListPagination(PageNumberPagination):
    """Default page_size 25, clamp to 100 so the queue doesn't pull a
    huge slab into memory on badly-behaved clients."""
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class ImportSessionListView(APIView):
    """``GET /api/core/imports/v2/sessions/`` (and ``/api/core/etl/v2/sessions/``)

    Paginated list of v2 sessions scoped to the request's tenant.
    Drives the queue panel on the Imports hub page (Phase 6.z-b).

    Query params:
      * ``status=analyzing,committing`` — comma-separated whitelist.
      * ``mode=template|etl`` — filter by mode.
      * ``page_size=N`` — up to ``_ImportSessionListPagination.max_page_size``.

    Returns the DRF-paginated shape: ``{count, next, previous, results}``.
    Each result is shaped by :class:`ImportSessionListSerializer` —
    deliberately lightweight (no ``parsed_payload`` / ``open_issues``
    / ``result``, which can be multi-MB per row).

    Cross-tenant sessions are invisible (not 403) — matches the detail
    endpoint's contract.
    """

    def get_permissions(self):
        return _perms()

    def get(self, request, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err

        qs = ImportSession.objects.all().select_related(
            "created_by", "transformation_rule",
        )
        if company_id is not None:
            qs = qs.filter(company_id=company_id)

        status_raw = request.GET.get("status")
        if status_raw:
            valid = {s for s, _ in ImportSession.STATUS_CHOICES}
            requested = [
                s.strip() for s in status_raw.split(",") if s.strip() in valid
            ]
            if requested:
                qs = qs.filter(status__in=requested)

        mode = request.GET.get("mode")
        if mode in {ImportSession.MODE_TEMPLATE, ImportSession.MODE_ETL}:
            qs = qs.filter(mode=mode)

        # Newest first — that's the interesting end for the queue.
        qs = qs.order_by("-created_at")

        paginator = _ImportSessionListPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = ImportSessionListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ImportSessionRunningCountView(APIView):
    """``GET /api/core/imports/v2/sessions/running-count/``

    Single aggregate used by the sidebar badge — polls this every
    ~10s while the sidebar is mounted. Returns per-status counts of
    non-terminal sessions (``analyzing``, ``committing``,
    ``awaiting_resolve``) plus a ``total`` convenience field.

    One ``GROUP BY status`` query, index-backed by
    ``company,status,-created_at``. Stays fast with tens of thousands
    of historical sessions because the filter+index keep the scan
    bounded to the few dozen non-terminal rows.
    """

    def get_permissions(self):
        return _perms()

    def get(self, request, tenant_id: Optional[int] = None) -> Response:
        company_id, err = _resolve_bulk_import_company_id(request)
        if err is not None:
            return err

        qs = ImportSession.objects.all()
        if company_id is not None:
            qs = qs.filter(company_id=company_id)

        running_statuses = [
            ImportSession.STATUS_ANALYZING,
            ImportSession.STATUS_COMMITTING,
            ImportSession.STATUS_AWAITING_RESOLVE,
        ]
        qs = qs.filter(status__in=running_statuses)

        buckets = dict(
            qs.values("status").annotate(n=Count("id")).values_list("status", "n")
        )
        payload = {
            "analyzing": buckets.get(ImportSession.STATUS_ANALYZING, 0),
            "committing": buckets.get(ImportSession.STATUS_COMMITTING, 0),
            "awaiting_resolve": buckets.get(ImportSession.STATUS_AWAITING_RESOLVE, 0),
        }
        payload["total"] = sum(payload.values())
        return Response(payload)
