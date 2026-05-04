"""DRF views for the agent app.

Two clusters:

1. **Connection** — superuser-only. ``/api/agent/connection/{,/import-tokens}``.
   Manages the singleton :class:`OpenAITokenStore`. The OAuth dance itself
   happens client-side (``python manage.py openai_oauth_login``); this
   surface only accepts the resulting tokens for storage.
2. **Chat** — any authenticated tenant user. ``/api/agent/conversations/``
   list/detail + ``.../chat/`` to send a message and receive the agent's
   reply. Scoped to ``(request.user, request.tenant)``.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Count
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.permissions import IsSuperUser

from .models import AgentConversation, AgentMessage, OpenAITokenStore
from .serializers import (
    AgentConversationDetailSerializer,
    AgentConversationSerializer,
    AgentMessageSerializer,
    OpenAIConnectionStatusSerializer,
)
from .services import oauth_service

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection (superuser-only)
# ---------------------------------------------------------------------------
class OpenAIConnectionView(APIView):
    """GET = status, DELETE = revoke. Superuser-only."""

    permission_classes = [IsSuperUser]

    def get(self, request):
        store = OpenAITokenStore.current() or OpenAITokenStore(id=0)
        ser = OpenAIConnectionStatusSerializer(store)
        return Response(ser.data)

    def delete(self, request):
        store = OpenAITokenStore.current()
        if store is None:
            return Response({"detail": "Nothing to disconnect."}, status=status.HTTP_200_OK)
        store.clear()
        store.connected_by = None
        store.connected_at = None
        store.chatgpt_account_id = ""
        store.last_error = ""
        store.save()
        log.info("agent.oauth.revoked by user=%s", request.user.id)
        return Response({"detail": "Disconnected."})


class _ImportTokensSerializer(serializers.Serializer):
    """Payload accepted by :class:`OpenAIConnectionImportTokensView`.

    Mirrors the dict the ``openai_oauth_login`` mgmt command POSTs after
    completing the loopback OAuth dance. ``chatgpt_account_id`` is the
    only true secret-derived field we care about beyond the tokens
    themselves; ``account_email`` is cosmetic."""

    access_token = serializers.CharField(max_length=8192)
    refresh_token = serializers.CharField(max_length=8192, required=False, allow_blank=True)
    expires_in = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    chatgpt_account_id = serializers.CharField(max_length=255)
    account_email = serializers.CharField(max_length=255, required=False, allow_blank=True)
    id_token = serializers.CharField(max_length=8192, required=False, allow_blank=True)


class OpenAIConnectionImportTokensView(APIView):
    """POST: accept tokens obtained client-side via the loopback OAuth flow.

    The CLI (``python manage.py openai_oauth_login``) does the dance against
    OpenAI's auth server, then POSTs the result here. Superuser-only.

    We never see the OAuth code or PKCE verifier — only the final tokens
    the OAuth server granted them. This keeps Sysnord out of the OAuth
    redirect path entirely (which is needed because OpenAI's Codex
    ``client_id`` is locked to ``http://localhost:1455/auth/callback``)."""

    permission_classes = [IsSuperUser]

    def post(self, request):
        ser = _ImportTokensSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        try:
            store = oauth_service.persist_tokens(
                access_token=v["access_token"],
                refresh_token=v.get("refresh_token") or None,
                expires_in=v.get("expires_in"),
                chatgpt_account_id=v["chatgpt_account_id"],
                account_email=v.get("account_email", ""),
                id_token=v.get("id_token") or None,
                connected_by=request.user,
            )
        except Exception as exc:
            log.exception("agent.oauth.import_tokens failed: %s", exc)
            return Response(
                {"detail": f"Failed to persist tokens: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        log.info(
            "agent.oauth.connected_via_cli account=%s by user=%s",
            store.account_email or store.chatgpt_account_id, request.user.id,
        )
        return Response(OpenAIConnectionStatusSerializer(store).data)


# ---------------------------------------------------------------------------
# Chat (authenticated tenant users)
# ---------------------------------------------------------------------------
class AgentConversationViewSet(viewsets.ModelViewSet):
    """List/create/retrieve/delete agent conversations for the calling user
    inside the active tenant.

    Privacy: the queryset is filtered by both ``request.user`` and
    ``request.tenant`` (set by ``multitenancy.middleware.TenantMiddleware``).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = AgentConversationSerializer

    def get_queryset(self):
        tenant = getattr(self.request, "tenant", None)
        qs = AgentConversation.objects.filter(user=self.request.user)
        if tenant is not None:
            qs = qs.filter(company=tenant)
        return qs.annotate(messages_count=Count("messages")).order_by("-updated_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return AgentConversationDetailSerializer
        return AgentConversationSerializer

    def perform_create(self, serializer):
        tenant = getattr(self.request, "tenant", None)
        if tenant is None:
            raise ValueError("Cannot create conversation without an active tenant.")
        serializer.save(user=self.request.user, company=tenant)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}

    @action(detail=True, methods=["post"], url_path="attachments")
    def upload_attachment(self, request, pk=None, **kwargs):
        """Accept one file per call (multipart/form-data, field 'file').

        Stores it on the configured ``MEDIA_ROOT`` (Railway Volume in
        production), classifies by extension/content-type, and returns
        ``{id, kind, content_type, size_bytes, filename}``. The chat
        endpoint then references the returned ``id`` via
        ``attachment_ids: [...]``.
        """
        from django.conf import settings as _settings

        from .models import AgentMessageAttachment

        conversation = self.get_object()
        file_obj = request.FILES.get("file")
        if file_obj is None:
            return Response(
                {"detail": "file field is required (multipart/form-data)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = int(getattr(_settings, "AGENT_ATTACHMENT_MAX_BYTES", 25 * 1024 * 1024))
        if file_obj.size > max_bytes:
            return Response(
                {"detail": f"File too large ({file_obj.size} > {max_bytes} bytes)."},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        ct = (file_obj.content_type or "").lower()
        name_lower = (file_obj.name or "").lower()
        # Classify by content-type and filename. Be liberal with NF-e XML
        # since some browsers report ``text/xml``, others ``application/xml``,
        # OFX is sometimes ``text/plain``.
        if "xml" in ct or name_lower.endswith(".xml"):
            kind = AgentMessageAttachment.KIND_NFE_XML
        elif name_lower.endswith(".ofx") or "ofx" in ct:
            kind = AgentMessageAttachment.KIND_OFX
        elif ct == "application/pdf" or name_lower.endswith(".pdf"):
            kind = AgentMessageAttachment.KIND_PDF
        elif ct.startswith("image/") or any(name_lower.endswith(e) for e in (".png", ".jpg", ".jpeg", ".webp", ".gif")):
            kind = AgentMessageAttachment.KIND_IMAGE
        else:
            kind = AgentMessageAttachment.KIND_OTHER

        att = AgentMessageAttachment.objects.create(
            company=conversation.company,
            conversation=conversation,
            file=file_obj,
            filename=file_obj.name[:255],
            content_type=ct[:128],
            size_bytes=file_obj.size,
            kind=kind,
        )
        return Response({
            "id": att.id,
            "kind": att.kind,
            "filename": att.filename,
            "content_type": att.content_type,
            "size_bytes": att.size_bytes,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="chat")
    def chat(self, request, pk=None, **kwargs):
        """Send a user message and receive the agent's reply.

        ``**kwargs`` swallows the ``tenant_id`` URL capture that
        ``TenantMiddleware`` relies on — without it DRF raises
        ``TypeError: chat() got an unexpected keyword argument 'tenant_id'``
        when the route is mounted under ``/<tenant_id>/api/agent/``.

        Persists the user turn, runs the LLM ↔ tools loop synchronously,
        and returns the full set of new messages produced (user +
        intermediate tool turns + final assistant). The frontend renders
        them in order; intermediate messages are useful as "thinking…"
        affordances ("agent is reading transactions…").
        """
        from .services.agent_runtime import (
            AgentRuntimeError,
            SysnordAgent,
        )

        conversation = self.get_object()
        body = request.data or {}
        content = (body.get("content") or "").strip()
        if not content:
            return Response(
                {"detail": "content is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Optional per-turn overrides for the conversation's persisted
        # config. Useful when the user changes the model in the widget
        # mid-thread without committing it to the conversation row.
        config_changed_fields: list[str] = []
        for fname in ("model", "reasoning_effort"):
            if fname in body and body.get(fname) != getattr(conversation, fname):
                setattr(conversation, fname, body.get(fname) or "")
                config_changed_fields.append(fname)
        if "include_page_context" in body and bool(body["include_page_context"]) != conversation.include_page_context:
            conversation.include_page_context = bool(body["include_page_context"])
            config_changed_fields.append("include_page_context")

        # ``page_context``: only honoured if the conversation opts in. The
        # runtime double-checks via the conversation flag; we forward the
        # blob unconditionally and let it decide.
        page_context = body.get("page_context") if conversation.include_page_context else None

        # Optional list of pre-uploaded attachment IDs to bind to this turn.
        # Uploads happen via the dedicated ``/attachments/`` endpoint and
        # return ``{id, ...}``; the chat call references them so the
        # runtime can wire each one into the LLM's input items.
        attachment_ids = body.get("attachment_ids") or []
        if attachment_ids and not isinstance(attachment_ids, list):
            return Response(
                {"detail": "attachment_ids must be a list of integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import AgentMessageAttachment
        attachments_qs = AgentMessageAttachment.objects.filter(
            id__in=attachment_ids,
            conversation=conversation,
            message__isnull=True,  # only un-bound attachments
        )

        with transaction.atomic():
            if config_changed_fields:
                conversation.save(update_fields=config_changed_fields + ["updated_at"])
            user_msg = AgentMessage.objects.create(
                company=conversation.company,
                conversation=conversation,
                role=AgentMessage.ROLE_USER,
                content=content,
            )
            # Bind attachments to this turn's user message.
            attachments_qs.update(message=user_msg)
            if not conversation.title:
                conversation.title = content[:80]
                conversation.save(update_fields=["title", "updated_at"])

        try:
            result = SysnordAgent(
                conversation, page_context=page_context,
            ).run_turn(user_message=user_msg)
        except AgentRuntimeError as exc:
            log.warning(
                "agent.chat.runtime_error conv=%s user=%s: %s",
                conversation.id, request.user.id, exc,
            )
            return Response(
                {
                    "detail": str(exc),
                    "messages": [AgentMessageSerializer(user_msg).data],
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        new_messages = [user_msg, *result.intermediate_messages, result.final_message]
        return Response({
            "iterations": result.iterations,
            "truncated": result.truncated,
            "messages": AgentMessageSerializer(new_messages, many=True).data,
        })


# ---------------------------------------------------------------------------
# Tool catalog (read-only)
# ---------------------------------------------------------------------------
class AgentToolCatalogView(APIView):
    """GET /api/agent/tools/ — exposes the MCP tool registry."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from mcp_server.tools import TOOLS

        return Response({
            "count": len(TOOLS),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in TOOLS
            ],
        })


class AgentAuditToolCallsView(APIView):
    """GET /api/agent/audit/tool-calls/ — read-only view onto
    :class:`agent.models.AgentToolCallLog`.

    Filters via query string:
      * ``conversation`` (id)
      * ``tool`` (name, exact)
      * ``status`` (ok/warn/error/rejected)
      * ``since`` (ISO datetime, returns rows newer than this)
      * ``limit`` (default 100, max 500)

    Tenant-scoped via ``request.tenant``. Args summaries are already
    truncated at write time (PII risk bounded), so this surface can
    safely surface them to operators without further sanitisation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, **kwargs):
        from .models import AgentToolCallLog

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response({"detail": "tenant not set"}, status=400)

        qs = AgentToolCallLog.objects.filter(company=tenant)
        conv_id = request.query_params.get("conversation")
        if conv_id:
            qs = qs.filter(conversation_id=conv_id)
        tool = request.query_params.get("tool")
        if tool:
            qs = qs.filter(tool_name=tool)
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        since = request.query_params.get("since")
        if since:
            try:
                from django.utils.dateparse import parse_datetime
                dt = parse_datetime(since)
                if dt:
                    qs = qs.filter(created_at__gte=dt)
            except Exception:
                pass
        limit = min(int(request.query_params.get("limit", 100) or 100), 500)

        rows = [
            {
                "id": r.id,
                "tool_name": r.tool_name,
                "tool_domain": r.tool_domain,
                "status": r.status,
                "args_summary": r.args_summary,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "latency_ms": r.latency_ms,
                "response_size_bytes": r.response_size_bytes,
                "iteration": r.iteration,
                "conversation_id": r.conversation_id,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in qs.order_by("-created_at", "-id")[:limit]
        ]
        return Response({"count": len(rows), "tool_calls": rows})


class AgentAuditWritesView(APIView):
    """GET /api/agent/audit/writes/ — read-only view onto
    :class:`agent.models.AgentWriteAudit`.

    Same filter shape as the tool-calls view. Includes
    ``before_state`` and ``after_state`` JSON blobs for full replay
    context — these can grow large, so use pagination.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, **kwargs):
        from .models import AgentWriteAudit

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return Response({"detail": "tenant not set"}, status=400)

        qs = AgentWriteAudit.objects.filter(company=tenant)
        conv_id = request.query_params.get("conversation")
        if conv_id:
            qs = qs.filter(conversation_id=conv_id)
        tool = request.query_params.get("tool")
        if tool:
            qs = qs.filter(tool_name=tool)
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)
        limit = min(int(request.query_params.get("limit", 50) or 50), 200)

        rows = [
            {
                "id": r.id,
                "tool_name": r.tool_name,
                "target_model": r.target_model,
                "target_ids": r.target_ids,
                "args_summary": r.args_summary,
                "before_state": r.before_state,
                "after_state": r.after_state,
                "status": r.status,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "undo_token": r.undo_token,
                "conversation_id": r.conversation_id,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat(),
            }
            for r in qs.order_by("-created_at", "-id")[:limit]
        ]
        return Response({"count": len(rows), "writes": rows})


class AgentModelsCatalogView(APIView):
    """GET /api/agent/models/ — what the model dropdown shows.

    Read-only, any authenticated user. The list is curated in
    :mod:`agent.services.models_catalog`; we don't auto-discover from
    OpenAI because the Codex API doesn't expose the metadata we want
    (context window, reasoning support).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings as _settings
        from agent.services.models_catalog import catalog_payload

        return Response(catalog_payload(
            default_model=getattr(_settings, "OPENAI_DEFAULT_MODEL", "gpt-5.5"),
        ))
