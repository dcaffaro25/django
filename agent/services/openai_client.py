"""HTTP client for OpenAI's Chat Completions API.

Thin wrapper around ``requests``. The two non-trivial responsibilities:

* **Auth**: bearer-token comes from :class:`OpenAITokenStore`, refreshed
  via :mod:`agent.services.oauth_service` on a 401. We try the refresh
  exactly once before giving up — repeated 401s after a fresh access
  token mean the upstream account/scope is broken, not a stale token,
  and chasing them in a loop only delays the operator's "reconnect"
  fix.
* **Schema massaging**: the chat-completions spec wraps tool definitions
  in ``{"type":"function","function":{...}}``; we build that envelope
  from the simpler :class:`mcp_server.tools.ToolDef` so callers don't
  have to.

The client itself is **stateless** between calls — every
``chat_completions`` reads the singleton store fresh. That keeps the
multi-user, multi-thread case correct (Phase 2b runs the agent loop
synchronously per HTTP request, so any number of users can share the
one token without interleaving issues — OpenAI's rate limit is the
real constraint).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests
from django.conf import settings

from agent.models import OpenAITokenStore
from agent.services import oauth_service

log = logging.getLogger(__name__)


class OpenAIClientError(RuntimeError):
    """Generic API error after exhausting refresh + retry."""


class OpenAINotConnected(OpenAIClientError):
    """No token in the store. Operator must connect first."""


class OpenAIReconnectRequired(OpenAIClientError):
    """Refresh failed (or 401 persisted after refresh). Operator must
    reconnect through the admin page; we cannot recover automatically."""


def _api_url(path: str) -> str:
    base = getattr(settings, "OPENAI_API_BASE_URL", "https://api.openai.com").rstrip("/")
    return f"{base}{path}"


def _build_tool_specs(tools_subset: list[str] | None = None) -> list[dict[str, Any]]:
    """Translate :data:`mcp_server.tools.TOOLS` into OpenAI's
    ``functions``-style envelope. Pass ``tools_subset`` to restrict to
    a named subset (useful for per-conversation tool gating)."""
    from mcp_server.tools import TOOLS

    chosen = TOOLS
    if tools_subset is not None:
        wanted = set(tools_subset)
        chosen = [t for t in TOOLS if t.name in wanted]

    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in chosen
    ]


class OpenAIClient:
    """Thin Chat Completions wrapper.

    Construct once per request handler; the inner state (the
    :class:`OpenAITokenStore` row) is always fetched fresh so multiple
    concurrent requests stay in sync.
    """

    def __init__(self):
        self._timeout = float(getattr(settings, "OPENAI_REQUEST_TIMEOUT", 60))

    # ------------------------------------------------------------------
    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """Make one Chat Completions call. Returns the parsed response.

        Raises :class:`OpenAINotConnected` if the singleton store is
        empty, :class:`OpenAIReconnectRequired` if a refresh + retry
        cycle still 401s, :class:`OpenAIClientError` for other API
        errors.
        """
        store = OpenAITokenStore.current()
        if store is None or not store.is_connected:
            raise OpenAINotConnected(
                "OpenAI is not connected. A platform superuser must "
                "complete the OAuth flow before the agent can run."
            )

        body: dict[str, Any] = {
            "model": model or getattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-4o-mini"),
            "messages": messages,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if temperature is not None:
            body["temperature"] = temperature

        # First attempt with the current access token.
        resp = self._post(store, body)
        if resp.status_code != 401:
            return self._parse(resp)

        # 401 → try ONE refresh, then ONE retry.
        log.info("agent.openai.401 — attempting token refresh")
        try:
            store = oauth_service.refresh_access_token(store=store)
        except oauth_service.OAuthExchangeError as exc:
            raise OpenAIReconnectRequired(
                f"OpenAI token refresh failed: {exc}. Operator must reconnect."
            ) from exc

        resp = self._post(store, body)
        if resp.status_code == 401:
            store.last_error = "Persistent 401 after refresh"
            store.save(update_fields=["last_error", "updated_at"])
            raise OpenAIReconnectRequired(
                "Still 401 after refresh; account or scope changed. Reconnect required."
            )
        return self._parse(resp)

    # ------------------------------------------------------------------
    def _post(self, store: OpenAITokenStore, body: dict[str, Any]):
        access_token, _ = store.tokens()
        try:
            return requests.post(
                _api_url("/v1/chat/completions"),
                headers={
                    "Authorization": f"{store.token_type or 'Bearer'} {access_token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(body),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise OpenAIClientError(f"OpenAI API unreachable: {exc}") from exc

    @staticmethod
    def _parse(resp) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise OpenAIClientError(
                f"OpenAI API returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise OpenAIClientError(f"OpenAI API returned non-JSON: {resp.text[:200]}") from exc


# Convenience export so the agent runtime can stay tool-spec free.
build_tool_specs = _build_tool_specs
