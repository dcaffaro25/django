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

    @action(detail=True, methods=["post"], url_path="chat")
    def chat(self, request, pk=None):
        """Send a user message and receive the agent's reply.

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
        content = (request.data or {}).get("content", "").strip()
        if not content:
            return Response(
                {"detail": "content is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            user_msg = AgentMessage.objects.create(
                company=conversation.company,
                conversation=conversation,
                role=AgentMessage.ROLE_USER,
                content=content,
            )
            # Auto-title from the first user message; bounded to 80 chars.
            if not conversation.title:
                conversation.title = content[:80]
                conversation.save(update_fields=["title", "updated_at"])

        try:
            result = SysnordAgent(conversation).run_turn(user_message=user_msg)
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
