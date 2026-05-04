"""HTTP client for OpenAI's Codex Responses API.

This is **not** the standard ``api.openai.com/v1/chat/completions``
endpoint — that one rejects the ChatGPT-subscription OAuth tokens we
get from the loopback flow. The Codex CLI / OpenClaw / Claude Code all
hit the unofficial-but-stable endpoint at ``chatgpt.com/backend-api/codex``,
which:

* Accepts the OAuth ``access_token`` as a bearer
* Requires ``chatgpt-account-id`` header (extracted from the JWT and
  persisted in :class:`OpenAITokenStore.chatgpt_account_id`)
* Requires ``originator`` header from a whitelisted set
  (``codex_cli_rs``, ``codex_vscode``, ``codex_sdk_ts``, or any value
  starting with ``Codex``). pi-mono uses ``pi`` and gets 403; we use
  ``codex_cli_rs`` to be safe — settings can override.
* Requires ``OpenAI-Beta: responses=experimental``
* Uses Server-Sent Events (``stream: true`` is mandatory). We consume
  the stream synchronously inside the request handler and return the
  fully-assembled response to the agent loop.

Refs:
  * https://github.com/badlogic/pi-mono/blob/main/packages/ai/src/providers/openai-codex-responses.ts
  * https://github.com/badlogic/pi-mono/issues/1828 (originator whitelist)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterable

import requests
from django.conf import settings

from agent.models import OpenAITokenStore
from agent.services import oauth_service

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hardcoded Codex API constants
# ---------------------------------------------------------------------------
DEFAULT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
DEFAULT_RESPONSES_PATH = "/responses"
# OpenAI's auth server whitelists first-party originators on the API side:
# codex_cli_rs / codex_vscode / codex_sdk_ts / Codex* — any other value
# returns 403. ``codex_cli_rs`` is the safest because it's actively used
# by the official Rust CLI.
DEFAULT_ORIGINATOR = "codex_cli_rs"
DEFAULT_OPENAI_BETA = "responses=experimental"
DEFAULT_USER_AGENT = "sysnord-agent/1.0"


class OpenAIClientError(RuntimeError):
    """Generic API error after exhausting refresh + retry."""


class OpenAINotConnected(OpenAIClientError):
    """No token in the store. Operator must run the OAuth login first."""


class OpenAIReconnectRequired(OpenAIClientError):
    """Refresh failed (or 401 persisted after refresh). Operator must
    re-run ``python manage.py openai_oauth_login`` from their machine."""


# ---------------------------------------------------------------------------
# Tool spec building (Codex Responses format)
# ---------------------------------------------------------------------------
def build_tool_specs(tools_subset: list[str] | None = None) -> list[dict[str, Any]]:
    """Translate :data:`mcp_server.tools.TOOLS` into Responses-API tool format.

    Note: Responses API tools are flat objects with ``type: function`` at
    the top level (vs. Chat Completions which nests under
    ``{"type":"function","function":{...}}``)."""
    from mcp_server.tools import TOOLS

    chosen = TOOLS
    if tools_subset is not None:
        wanted = set(tools_subset)
        chosen = [t for t in TOOLS if t.name in wanted]

    return [
        {
            "type": "function",
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
            "strict": False,
        }
        for t in chosen
    ]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class OpenAIClient:
    """Synchronous Codex Responses client.

    Each call reads the singleton :class:`OpenAITokenStore` fresh, so a
    refresh in one request doesn't lag another. Concurrency is bounded
    by OpenAI's rate limit, not by this client.
    """

    def __init__(self):
        self._timeout = float(getattr(settings, "OPENAI_REQUEST_TIMEOUT", 120))
        self._base_url = getattr(settings, "OPENAI_CODEX_BASE_URL", DEFAULT_CODEX_BASE_URL)
        self._responses_path = getattr(
            settings, "OPENAI_CODEX_RESPONSES_PATH", DEFAULT_RESPONSES_PATH,
        )
        self._originator = getattr(settings, "OPENAI_CODEX_ORIGINATOR", DEFAULT_ORIGINATOR)
        self._beta = getattr(settings, "OPENAI_CODEX_BETA", DEFAULT_OPENAI_BETA)
        self._user_agent = getattr(settings, "OPENAI_CODEX_USER_AGENT", DEFAULT_USER_AGENT)

    # ------------------------------------------------------------------
    def respond(
        self,
        *,
        instructions: str,
        input_items: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Make one Codex Responses call. Returns a normalised dict::

            {
                "model": "...",
                "output": [<list of typed items: message / function_call / reasoning>],
                "usage": {"input_tokens": N, "output_tokens": M, "total_tokens": K},
            }

        The Responses API streams via SSE; we accumulate the events and
        return the final assembled response. Raises:

        * :class:`OpenAINotConnected` if the singleton store is empty
        * :class:`OpenAIReconnectRequired` if a refresh + retry cycle still
          401s
        * :class:`OpenAIClientError` for other API errors
        """
        store = OpenAITokenStore.current()
        if store is None or not store.is_connected:
            raise OpenAINotConnected(
                "OpenAI is not connected. Run "
                "`python manage.py openai_oauth_login` first."
            )
        if not store.chatgpt_account_id:
            raise OpenAINotConnected(
                "Stored token has no chatgpt_account_id — re-run the OAuth login."
            )

        body: dict[str, Any] = {
            "model": model or getattr(settings, "OPENAI_DEFAULT_MODEL", "gpt-5"),
            "store": False,
            "stream": True,
            "instructions": instructions,
            "input": input_items,
            "text": {"verbosity": "medium"},
            "tool_choice": "auto",
            "parallel_tool_calls": True,
        }
        if tools:
            body["tools"] = tools
        if session_id:
            body["prompt_cache_key"] = session_id

        # First attempt
        response_or_status = self._stream_call(store, body, session_id=session_id)
        if isinstance(response_or_status, dict):
            return response_or_status

        # 401 → refresh + retry once
        if response_or_status == 401:
            log.info("agent.openai.401 — attempting token refresh")
            try:
                store = oauth_service.refresh_and_persist(store=store)
            except oauth_service.OAuthExchangeError as exc:
                raise OpenAIReconnectRequired(
                    f"Token refresh failed: {exc}. Re-run openai_oauth_login."
                ) from exc

            response_or_status = self._stream_call(store, body, session_id=session_id)
            if isinstance(response_or_status, dict):
                return response_or_status
            if response_or_status == 401:
                store.last_error = "Persistent 401 after refresh"
                store.save(update_fields=["last_error", "updated_at"])
                raise OpenAIReconnectRequired(
                    "Still 401 after refresh; account or scope changed. Reconnect required."
                )

        raise OpenAIClientError(f"Codex API returned status {response_or_status}")

    # ------------------------------------------------------------------
    def _stream_call(
        self,
        store: OpenAITokenStore,
        body: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any] | int:
        """Run one streaming call. Returns the assembled response dict on
        success, or the HTTP status code (int) on auth/non-2xx failure so
        the caller can decide whether to retry."""
        access_token, _ = store.tokens()
        headers = {
            "Authorization": f"Bearer {access_token}",
            "chatgpt-account-id": store.chatgpt_account_id,
            "originator": self._originator,
            "User-Agent": self._user_agent,
            "OpenAI-Beta": self._beta,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        if session_id:
            headers["session_id"] = session_id
            headers["x-client-request-id"] = session_id

        url = f"{self._base_url.rstrip('/')}{self._responses_path}"
        try:
            resp = requests.post(
                url,
                data=json.dumps(body),
                headers=headers,
                timeout=self._timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            raise OpenAIClientError(f"Codex API unreachable: {exc}") from exc

        if resp.status_code == 401:
            try:
                resp.close()
            except Exception:
                pass
            return 401
        if resp.status_code >= 400:
            body_preview = resp.text[:500] if resp.content else "<empty>"
            try:
                resp.close()
            except Exception:
                pass
            raise OpenAIClientError(
                f"Codex API returned {resp.status_code}: {body_preview}"
            )

        try:
            return _assemble_sse_response(_iter_sse_events(resp))
        finally:
            try:
                resp.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------
def _iter_sse_events(resp: requests.Response) -> Iterable[dict[str, Any]]:
    """Yield each SSE ``data: {…}`` event as a parsed dict.

    The Responses API encodes one JSON object per SSE event. We ignore
    other SSE fields (event:, id:, retry:) since the payload itself
    carries the event ``type``."""
    buffer: list[str] = []
    for raw_line in resp.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        line = raw_line.rstrip("\r")
        if line == "":
            if not buffer:
                continue
            payload = "".join(buffer)
            buffer.clear()
            try:
                yield json.loads(payload)
            except json.JSONDecodeError:
                log.debug("agent.openai.sse.bad_json: %r", payload[:200])
            continue
        if line.startswith(":"):
            # SSE comment, ignore
            continue
        if line.startswith("data: "):
            buffer.append(line[len("data: "):])
        elif line.startswith("data:"):
            buffer.append(line[len("data:"):])
        # Other prefixes (event:, id:, retry:) are ignored.


def _assemble_sse_response(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Walk SSE events and produce the final ``{model, output, usage}``.

    Codex Responses emits events of types like ``response.created``,
    ``response.output_item.added``, ``response.output_item.done``, and
    finally ``response.completed``. We accept either:
      * a single ``response.completed`` event whose ``response`` object
        carries the full ``output`` array (preferred), or
      * incremental ``response.output_item.done`` events that we collect
        in order (fallback for transports that don't bundle the final).
    """
    final_response: dict[str, Any] | None = None
    items_in_order: list[dict[str, Any]] = []

    for event in events:
        etype = event.get("type")
        if etype == "response.completed":
            final_response = event.get("response") or {}
        elif etype == "response.output_item.done":
            item = event.get("item")
            if isinstance(item, dict):
                items_in_order.append(item)
        elif etype == "response.failed":
            err = event.get("response", {}).get("error") or event.get("error") or {}
            raise OpenAIClientError(
                f"Codex API streamed a failure: {err.get('message') or err}"
            )

    if final_response and isinstance(final_response.get("output"), list):
        out = final_response
    else:
        out = {"output": items_in_order}

    return {
        "model": (final_response or {}).get("model", ""),
        "output": out.get("output") or [],
        "usage": (final_response or {}).get("usage") or {},
    }
