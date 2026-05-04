"""OAuth 2.0 + PKCE bridge for OpenAI.

Implements the three operations the connection endpoints need:

* :func:`build_authorization_url` — picks a fresh state + PKCE pair, stores
  the verifier in :class:`agent.models.OAuthAuthorizationFlow`, returns the
  URL to redirect the superuser to.
* :func:`exchange_code` — consumes the authorization code at OpenAI's
  token endpoint, persists the tokens into the singleton
  :class:`OpenAITokenStore`, and decodes the ``id_token`` (if any) for the
  account email/sub displayed in the admin UI.
* :func:`refresh_access_token` — swaps the refresh token for a fresh
  access token. Called on demand by the OpenAI client when a 401 comes
  back from the API.

All three are pure-Python wrappers around ``requests``; settings keys live
in :mod:`nord_backend.settings` (``OPENAI_OAUTH_*``). The provider-specific
endpoints (``auth_url`` / ``token_url`` / ``client_id`` / scopes) are
configurable so this same module can serve any OAuth 2.0 + PKCE provider —
not just OpenAI's ChatGPT-Pro flow.
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

from agent.models import OAuthAuthorizationFlow, OpenAITokenStore

log = logging.getLogger(__name__)


class OAuthConfigError(RuntimeError):
    """Raised when OAuth settings are missing/invalid."""


class OAuthExchangeError(RuntimeError):
    """Raised when OpenAI's token endpoint refuses our code/refresh."""


# ---------------------------------------------------------------------------
# Settings access
# ---------------------------------------------------------------------------
def _setting(name: str, *, required: bool = False, default: str = "") -> str:
    value = getattr(settings, name, default)
    if required and not value:
        raise OAuthConfigError(
            f"{name} is not configured. Set it in environment / Django settings."
        )
    return value


def _config() -> dict[str, str]:
    return {
        "auth_url": _setting("OPENAI_OAUTH_AUTH_URL", required=True),
        "token_url": _setting("OPENAI_OAUTH_TOKEN_URL", required=True),
        "client_id": _setting("OPENAI_OAUTH_CLIENT_ID", required=True),
        "client_secret": _setting("OPENAI_OAUTH_CLIENT_SECRET", default=""),
        "redirect_uri": _setting("OPENAI_OAUTH_REDIRECT_URI", required=True),
        "scopes": _setting(
            "OPENAI_OAUTH_SCOPES",
            default="openid email profile offline_access",
        ),
    }


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------
def _new_code_verifier() -> str:
    """RFC 7636 §4.1: 43–128 chars of unreserved [A-Z, a-z, 0-9, -._~]."""
    return secrets.token_urlsafe(64)[:96]


def _code_challenge(verifier: str) -> str:
    """RFC 7636 §4.2: base64-url(SHA256(verifier)), no padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------
def build_authorization_url(*, user) -> tuple[str, OAuthAuthorizationFlow]:
    """Return ``(url, flow)`` — caller redirects the browser to ``url``.

    The flow row keeps the PKCE verifier server-side; we pass only the
    derived challenge to OpenAI. ``state`` doubles as CSRF token + key to
    look up the flow in ``/callback/``.
    """
    cfg = _config()

    OAuthAuthorizationFlow.cleanup_expired()  # opportunistic GC

    verifier = _new_code_verifier()
    flow = OAuthAuthorizationFlow.new(
        user=user,
        redirect_uri=cfg["redirect_uri"],
        code_verifier=verifier,
    )

    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": cfg["scopes"],
        "state": flow.state,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    url = f"{cfg['auth_url']}?{urlencode(params)}"
    return url, flow


# ---------------------------------------------------------------------------
# Code exchange
# ---------------------------------------------------------------------------
def exchange_code(
    *,
    state: str,
    code: str,
    user,
) -> OpenAITokenStore:
    """Validate state + exchange auth code for tokens. Persists the result
    in the singleton :class:`OpenAITokenStore` and returns it."""
    cfg = _config()

    try:
        flow = OAuthAuthorizationFlow.objects.get(state=state)
    except OAuthAuthorizationFlow.DoesNotExist as exc:
        raise OAuthExchangeError("Unknown OAuth state — request expired or replayed.") from exc

    if flow.is_expired:
        flow.delete()
        raise OAuthExchangeError("OAuth state expired. Restart the connection flow.")
    if flow.is_consumed:
        raise OAuthExchangeError("OAuth state already consumed.")

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": flow.redirect_uri,
        "client_id": cfg["client_id"],
        "code_verifier": flow.code_verifier,
    }
    if cfg["client_secret"]:
        payload["client_secret"] = cfg["client_secret"]

    log.info("agent.oauth.exchange_code state=%s user=%s", state[:8], user.id)
    resp = _post_token_endpoint(cfg["token_url"], payload)

    flow.consumed_at = timezone.now()
    flow.save(update_fields=["consumed_at", "updated_at"])

    store = OpenAITokenStore.get_or_create_singleton()
    store.set_tokens(
        access_token=resp["access_token"],
        refresh_token=resp.get("refresh_token"),
        token_type=resp.get("token_type", "Bearer"),
        expires_in=resp.get("expires_in"),
        scopes=resp.get("scope") or cfg["scopes"],
    )
    store.connected_by = user
    store.connected_at = timezone.now()

    # Best-effort: pull email/sub out of id_token. The id_token is a JWT;
    # we don't verify the signature here because we trust the TLS channel
    # to OpenAI for now (production should verify against the JWKS).
    id_token = resp.get("id_token")
    if id_token:
        claims = _decode_jwt_payload(id_token)
        store.account_email = claims.get("email", "") or ""
        store.account_subject = claims.get("sub", "") or ""

    store.save()
    return store


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
def refresh_access_token(*, store: OpenAITokenStore) -> OpenAITokenStore:
    """Use the stored refresh token to mint a new access token. Mutates +
    saves *store*. Raises :class:`OAuthExchangeError` if the refresh fails;
    the caller is expected to surface that as a "reconnection required"
    error to the operator."""
    cfg = _config()
    _, refresh_token = store.tokens()
    if not refresh_token:
        raise OAuthExchangeError("No refresh token stored — reconnection required.")

    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": cfg["client_id"],
    }
    if cfg["client_secret"]:
        payload["client_secret"] = cfg["client_secret"]

    try:
        resp = _post_token_endpoint(cfg["token_url"], payload)
    except OAuthExchangeError as exc:
        store.last_error = str(exc)[:4000]
        store.save(update_fields=["last_error", "updated_at"])
        raise

    store.set_tokens(
        access_token=resp["access_token"],
        refresh_token=resp.get("refresh_token") or refresh_token,
        token_type=resp.get("token_type", "Bearer"),
        expires_in=resp.get("expires_in"),
        scopes=resp.get("scope") or store.scopes,
    )
    store.save()
    return store


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _post_token_endpoint(url: str, payload: dict[str, str]) -> dict[str, Any]:
    timeout = float(getattr(settings, "OPENAI_OAUTH_HTTP_TIMEOUT", 15))
    try:
        resp = requests.post(
            url,
            data=payload,
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
        raise OAuthExchangeError(f"OAuth token endpoint returned non-JSON: {resp.text[:200]}") from exc


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode the *payload* segment of a JWT without signature verification.

    We only use this to read ``email``/``sub`` for display; auth comes
    from the access token, not from claims trust. A bad/garbled id_token
    silently yields ``{}``.
    """
    try:
        _, payload_b64, _ = token.split(".", 2)
    except ValueError:
        return {}
    # JWT base64-url, no padding
    pad = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + pad)
        return json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
