"""OAuth 2.1 + PKCE bridge for OpenAI's ChatGPT subscription.

Replicates OpenClaw / Codex CLI's OAuth flow (which is the canonical
implementation for "use my ChatGPT Pro subscription as the LLM"):

* Hardcoded ``CLIENT_ID`` registered against ``http://localhost:1455/auth/callback``
  — same one OpenClaw publishes in their open-source repo. Public client
  (no secret); auth bound by PKCE.
* Special query params required by OpenAI's auth server
  (``id_token_add_organizations=true``, ``codex_cli_simplified_flow=true``,
  ``originator=<app-id>``).
* Account ID extraction: the access_token is a JWT with a custom claim
  ``"https://api.openai.com/auth": {"chatgpt_account_id": "..."}``. That
  ``chatgpt_account_id`` is required as a header (``chatgpt-account-id``)
  on every subsequent API call, so we capture and persist it here.

Because the redirect URI is locked to loopback, the OAuth dance has to
happen on a machine that can bind ``127.0.0.1:1455``. That's done by the
``python manage.py openai_oauth_login`` management command; this module
just provides the building blocks (URL builder, code exchange, refresh).
The :class:`OpenAITokenStore` is then populated either:

* by the management command directly (when run on the same host as the
  Django DB), or
* via ``POST /api/agent/connection/import-tokens/`` (when run from the
  superuser's laptop against a remote Sysnord deployment).

Refs:
  * https://github.com/badlogic/pi-mono/blob/main/packages/ai/src/utils/oauth/openai-codex.ts
  * https://github.com/openclaw/openclaw/blob/main/docs/concepts/oauth.md
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.utils import timezone

from agent.models import OpenAITokenStore

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hardcoded constants (matching OpenClaw / Codex CLI)
# ---------------------------------------------------------------------------
# Public OAuth client_id registered by OpenAI for the Codex CLI flow. We
# share it with OpenClaw, Claude Code, and any other tool that uses the
# ChatGPT Pro subscription auth — it's a public client (PKCE-only, no
# secret). Settings can override for testing.
DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_AUTH_URL = "https://auth.openai.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://localhost:1455/auth/callback"
DEFAULT_SCOPES = "openid profile email offline_access"
# Identifies our app to OpenAI's auth server (NOT the API call originator).
# OpenClaw uses ``pi``; we use ``sysnord`` so accidental cross-app analytics
# stay separate. Override via OPENAI_OAUTH_ORIGINATOR if OpenAI tightens
# the whitelist on the auth side.
DEFAULT_ORIGINATOR = "sysnord"

# JWT claim path where OpenAI puts the chatgpt_account_id.
JWT_AUTH_CLAIM = "https://api.openai.com/auth"


class OAuthExchangeError(RuntimeError):
    """Raised when OpenAI's token endpoint refuses our code/refresh."""


class JwtDecodeError(RuntimeError):
    """Raised when we can't extract account info from an access_token."""


def _setting(name: str, default: str) -> str:
    return getattr(settings, name, default) or default


def _config() -> dict[str, str]:
    """Resolved OAuth config — defaults match OpenClaw, settings override."""
    return {
        "client_id": _setting("OPENAI_OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID),
        "auth_url": _setting("OPENAI_OAUTH_AUTH_URL", DEFAULT_AUTH_URL),
        "token_url": _setting("OPENAI_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL),
        "redirect_uri": _setting("OPENAI_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI),
        "scopes": _setting("OPENAI_OAUTH_SCOPES", DEFAULT_SCOPES),
        "originator": _setting("OPENAI_OAUTH_ORIGINATOR", DEFAULT_ORIGINATOR),
    }


# ---------------------------------------------------------------------------
# PKCE helpers (RFC 7636)
# ---------------------------------------------------------------------------
def new_code_verifier() -> str:
    """Cryptographically random 43–128 char URL-safe string."""
    return secrets.token_urlsafe(64)[:96]


def code_challenge_for(verifier: str) -> str:
    """``base64url(SHA256(verifier))`` with no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_state() -> str:
    """16-byte hex CSRF token (matches OpenClaw)."""
    return secrets.token_hex(16)


# ---------------------------------------------------------------------------
# Authorize URL
# ---------------------------------------------------------------------------
def build_authorize_url(*, state: str, code_verifier: str) -> str:
    """Build the URL the operator's browser should open. Mirrors OpenClaw's
    flow exactly — including the special query params OpenAI's auth server
    requires for the Codex subscription flow."""
    cfg = _config()
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg["scopes"],
        "state": state,
        "code_challenge": code_challenge_for(code_verifier),
        "code_challenge_method": "S256",
        # OpenAI-specific (required for ChatGPT subscription flow):
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": cfg["originator"],
    }
    return f"{cfg['auth_url']}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Code exchange
# ---------------------------------------------------------------------------
def exchange_code(*, code: str, code_verifier: str) -> dict[str, Any]:
    """POST the authorization code to OpenAI's token endpoint. Returns the
    parsed token response (caller is responsible for persistence)."""
    cfg = _config()
    body = {
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": cfg["redirect_uri"],
    }
    return _post_token(cfg["token_url"], body)


def refresh_token(*, refresh_token: str) -> dict[str, Any]:
    """Swap a refresh token for a fresh access token. Returns the new token
    response. Raises :class:`OAuthExchangeError` on any failure."""
    cfg = _config()
    body = {
        "grant_type": "refresh_token",
        "client_id": cfg["client_id"],
        "refresh_token": refresh_token,
    }
    return _post_token(cfg["token_url"], body)


# ---------------------------------------------------------------------------
# JWT account_id extraction
# ---------------------------------------------------------------------------
def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the *payload* segment of a JWT without signature verification.

    We trust the TLS channel to OpenAI for now; production should verify
    against the JWKS at https://auth.openai.com/.well-known/jwks.json.
    Returns ``{}`` for malformed tokens."""
    try:
        _, payload_b64, _ = token.split(".", 2)
    except ValueError:
        return {}
    pad = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}


def extract_account_id(access_token: str) -> str:
    """Pull ``chatgpt_account_id`` from the access_token's custom claim.

    The Codex Responses API rejects requests without this header — calling
    code MUST persist this value alongside the access token.

    Raises :class:`JwtDecodeError` if the token doesn't carry the claim
    (which would mean OpenAI changed the flow or the token came from a
    non-ChatGPT-subscription source)."""
    payload = decode_jwt_payload(access_token)
    auth_claim = payload.get(JWT_AUTH_CLAIM) or {}
    account_id = auth_claim.get("chatgpt_account_id") if isinstance(auth_claim, dict) else None
    if not account_id or not isinstance(account_id, str):
        raise JwtDecodeError(
            "Access token missing chatgpt_account_id claim. "
            "Is this a ChatGPT subscription token?"
        )
    return account_id


def extract_account_email(token: str) -> str:
    """Best-effort email extraction from the id_token (or access_token)
    payload. Returns ``""`` on any failure — only used for display."""
    payload = decode_jwt_payload(token)
    email = payload.get("email") if isinstance(payload, dict) else None
    return email if isinstance(email, str) else ""


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------
def persist_tokens(
    *,
    access_token: str,
    refresh_token: str | None,
    expires_in: int | None,
    chatgpt_account_id: str,
    account_email: str = "",
    id_token: str | None = None,
    connected_by=None,
) -> OpenAITokenStore:
    """Write a fresh tokenset to the singleton :class:`OpenAITokenStore`.

    Used by both the import-tokens endpoint and the local management
    command (when running against a same-host DB)."""
    store = OpenAITokenStore.get_or_create_singleton()
    store.set_tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=expires_in,
        scopes=_config()["scopes"],
    )
    store.chatgpt_account_id = chatgpt_account_id
    if account_email:
        store.account_email = account_email
    elif id_token:
        store.account_email = extract_account_email(id_token)
    if connected_by is not None:
        store.connected_by = connected_by
    store.connected_at = timezone.now()
    store.last_error = ""
    store.save()
    return store


def refresh_and_persist(*, store: OpenAITokenStore) -> OpenAITokenStore:
    """Use the stored refresh token to mint a fresh access token + re-extract
    accountId (in case the upstream account changed). Persists in place.

    Raises :class:`OAuthExchangeError` if refresh fails — the operator must
    re-run the OAuth dance from their machine."""
    _, refresh_tok = store.tokens()
    if not refresh_tok:
        raise OAuthExchangeError("No refresh token stored — reconnection required.")

    try:
        resp = refresh_token(refresh_token=refresh_tok)
    except OAuthExchangeError as exc:
        store.last_error = str(exc)[:4000]
        store.save(update_fields=["last_error", "updated_at"])
        raise

    new_access = resp["access_token"]
    new_refresh = resp.get("refresh_token") or refresh_tok
    expires_in = resp.get("expires_in")

    try:
        account_id = extract_account_id(new_access)
    except JwtDecodeError:
        # Fall back to the stored account_id; refresh shouldn't change it.
        account_id = store.chatgpt_account_id

    store.set_tokens(
        access_token=new_access,
        refresh_token=new_refresh,
        token_type=resp.get("token_type", "Bearer"),
        expires_in=expires_in,
        scopes=resp.get("scope") or store.scopes,
    )
    store.chatgpt_account_id = account_id
    store.last_error = ""
    store.save()
    return store


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _post_token(url: str, body: dict[str, str]) -> dict[str, Any]:
    timeout = float(getattr(settings, "OPENAI_OAUTH_HTTP_TIMEOUT", 15))
    try:
        resp = requests.post(
            url,
            data=body,  # OpenAI requires application/x-www-form-urlencoded
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise OAuthExchangeError(f"OAuth token endpoint unreachable: {exc}") from exc

    if resp.status_code >= 400:
        raise OAuthExchangeError(
            f"OAuth token endpoint returned {resp.status_code}: {resp.text[:500]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise OAuthExchangeError(
            f"OAuth token endpoint returned non-JSON: {resp.text[:200]}"
        ) from exc
