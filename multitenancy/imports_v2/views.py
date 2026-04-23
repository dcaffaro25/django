"""DRF views for the v2 template-import flow.

Phase 2 endpoints (mounted at ``/api/core/imports/v2/...``):

  * ``POST /analyze``            — upload file, create session.
  * ``GET /sessions/<id>``       — fetch session state.
  * ``DELETE /sessions/<id>``    — discard.
  * ``POST /commit/<id>``        — commit a ready session.

The ``/resolve/<id>`` endpoint ships in Phase 4. Until then a session
with blocking issues is stuck in ``awaiting_resolve`` and commit
returns 409.

All endpoints are tenant-scoped: the session's ``company_id`` must
match the request's resolved tenant. Cross-tenant access returns 404
(not 403 — we don't want to leak existence).
"""
from __future__ import annotations

from typing import Any, Optional

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.models import ImportSession
from multitenancy.views import _resolve_bulk_import_company_id

from . import services
from .serializers import ImportSessionSerializer


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

        session = services.analyze_template(
            company_id=company_id,
            user=request.user,
            file_bytes=file_bytes,
            file_name=file.name or "upload.xlsx",
            config=config,
        )
        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_201_CREATED,
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
            session = services.commit_session(session)
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
        except Exception as exc:  # pragma: no cover - delegated
            # Session was moved to ``error`` inside the service; surface
            # the reason to the client.
            return Response(
                {"error": str(exc), "type": type(exc).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            ImportSessionSerializer(session).data,
            status=status.HTTP_200_OK,
        )
