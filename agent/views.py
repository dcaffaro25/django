"""DRF views for the agent app.

Two clusters:

1. **Connection** — superuser-only. ``/api/agent/connection/{status,start,
   callback,revoke}/``. Manages the singleton :class:`OpenAITokenStore`.
2. **Chat** — any authenticated tenant user. ``/api/agent/conversations/``
   list/detail + ``.../chat/`` to send a message and receive the agent's
   reply. Scoped to ``(request.user, request.tenant)``.

The chat surface lives in this file but the actual agent loop is in
:mod:`agent.services.agent_runtime` (Phase 2). For now (Phase 1) the chat
endpoints reject with a clear message until the runtime ships, so the
frontend can be built against a known-good API shape.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponseRedirect
from rest_framework import permissions, status, viewsets
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
    """GET = status, DELETE = revoke. Superuser-only.

    The two POSTs (start + callback) are sibling :class:`APIView` classes
    because the OAuth callback is hit by the user's browser following a
    redirect, not by our SPA — keeping it on a separate route makes the
    URLconf clearer.
    """

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
        store.last_error = ""
        store.save()
        log.info("agent.oauth.revoked by user=%s", request.user.id)
        return Response({"detail": "Disconnected."})


class OpenAIConnectionStartView(APIView):
    """POST: start the PKCE flow, return the OpenAI authorization URL.

    The frontend should ``window.open(url)`` (or full-redirect) so the user
    lands on OpenAI's consent screen. After consent OpenAI sends them to
    :class:`OpenAIConnectionCallbackView`.
    """

    permission_classes = [IsSuperUser]

    def post(self, request):
        try:
            url, flow = oauth_service.build_authorization_url(user=request.user)
        except oauth_service.OAuthConfigError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response({"authorization_url": url, "state": flow.state})


class OpenAIConnectionCallbackView(APIView):
    """GET handler for the OAuth redirect.

    OpenAI sends the user back to this URL with ``?code=…&state=…``. We
    exchange the code for tokens and then redirect the browser to the
    admin page configured in ``settings.OPENAI_OAUTH_POST_CONNECT_REDIRECT``
    (or return JSON if no redirect target is set, useful for tests).

    Auth note: this endpoint cannot rely on the SPA's Authorization header
    — the browser is following a 302 from OpenAI. We require an
    authenticated session via Django's session middleware. ``IsSuperUser``
    is still enforced; if the cookie is gone we return 403 and the
    operator has to reconnect.
    """

    permission_classes = [IsSuperUser]

    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state")
        error = request.GET.get("error")
        error_desc = request.GET.get("error_description", "")

        if error:
            return self._fail(f"OpenAI returned error: {error} — {error_desc}")
        if not code or not state:
            return self._fail("Missing code/state in OAuth callback.")

        try:
            store = oauth_service.exchange_code(state=state, code=code, user=request.user)
        except oauth_service.OAuthExchangeError as exc:
            return self._fail(str(exc))
        except oauth_service.OAuthConfigError as exc:
            return self._fail(str(exc))

        log.info("agent.oauth.connected account=%s by user=%s", store.account_email, request.user.id)

        target = getattr(settings, "OPENAI_OAUTH_POST_CONNECT_REDIRECT", "")
        if target:
            return HttpResponseRedirect(f"{target}?connected=1")
        return Response({"detail": "Connected.", "account_email": store.account_email})

    def _fail(self, msg: str):
        target = getattr(settings, "OPENAI_OAUTH_POST_CONNECT_REDIRECT", "")
        if target:
            from urllib.parse import quote

            return HttpResponseRedirect(f"{target}?connected=0&error={quote(msg)}")
        return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


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
# Tool catalog (read-only, useful to the frontend so the widget can show
# what the agent is *capable* of without hitting the LLM).
# ---------------------------------------------------------------------------
class AgentToolCatalogView(APIView):
    """GET /api/agent/tools/ — exposes the MCP tool registry to the frontend.

    The widget uses this to render the "skills" hint above the chat input
    (e.g. "I can read accounts, list invoices, suggest reconciliations…").
    """

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
