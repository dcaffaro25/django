"""Models for the Sysnord internal agent.

Three concepts live here:

* :class:`OpenAITokenStore` — singleton row holding the *one* OAuth tokenset
  that the platform shares across all tenants and users. Tokens are
  encrypted at rest with Fernet (key in ``settings.AGENT_TOKEN_ENCRYPTION_KEY``).
* :class:`OAuthAuthorizationFlow` — short-lived scratchpad for the PKCE
  ``state``/``code_verifier`` between ``/start/`` and ``/callback/``. We
  keep them in DB instead of session so the OAuth callback works even when
  the user lands back without their session cookie (mobile browser quirks,
  popup-blocker fallbacks, etc.).
* :class:`AgentConversation` / :class:`AgentMessage` — chat history,
  tenant + user scoped.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from multitenancy.models import BaseModel, TenantAwareBaseModel


class OpenAITokenStore(BaseModel):
    """Singleton table — one row, ID 1 by convention — that holds the single
    OAuth tokenset the platform uses to call OpenAI on behalf of all users.

    The bearer token is short-lived (an hour-ish for OpenAI). The refresh
    token is the durable secret; we encrypt both at rest. ``last_error`` is
    populated when a refresh attempt fails so the admin UI can surface why
    the connection went stale.

    Only one row is ever expected; helper :meth:`current` returns it (or
    ``None`` when not connected). Creating extra rows isn't blocked at the
    DB level — the admin endpoints enforce the singleton invariant.
    """

    # Encrypted strings — set/read via :meth:`set_tokens`/:meth:`tokens`.
    # Stored as bytes (Fernet emits URL-safe base64 bytes).
    access_token_encrypted = models.BinaryField(blank=True)
    refresh_token_encrypted = models.BinaryField(blank=True)

    token_type = models.CharField(max_length=32, blank=True, default="Bearer")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scopes = models.CharField(max_length=512, blank=True, default="")

    # Identity payload from the IdToken claims (when the OAuth provider
    # returns one). Useful for the admin UI: "connected as foo@bar.com".
    account_email = models.CharField(max_length=255, blank=True, default="")
    account_subject = models.CharField(max_length=255, blank=True, default="")

    # ``chatgpt_account_id`` extracted from the access_token's
    # ``https://api.openai.com/auth`` claim. Required as the
    # ``chatgpt-account-id`` header on every Codex Responses API call —
    # without it the upstream returns 403/404. Re-derived on every refresh.
    chatgpt_account_id = models.CharField(max_length=255, blank=True, default="")

    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="openai_token_connections",
    )
    connected_at = models.DateTimeField(null=True, blank=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "OpenAI token store"
        verbose_name_plural = "OpenAI token store"

    def __str__(self):
        if not self.access_token_encrypted:
            return "OpenAITokenStore(disconnected)"
        return (
            f"OpenAITokenStore(account={self.account_email or '?'}, "
            f"expires_at={self.expires_at})"
        )

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------
    @staticmethod
    def _fernet():
        # Late import keeps cryptography off the hot path for tests that
        # never touch the token store.
        from cryptography.fernet import Fernet, InvalidToken  # noqa: F401

        key = getattr(settings, "AGENT_TOKEN_ENCRYPTION_KEY", "")
        if not key:
            raise RuntimeError(
                "AGENT_TOKEN_ENCRYPTION_KEY is not set. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and put it in env."
            )
        if isinstance(key, str):
            key = key.encode("utf-8")
        return Fernet(key)

    def set_tokens(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        token_type: str = "Bearer",
        expires_in: int | None = None,
        scopes: str = "",
    ) -> None:
        f = self._fernet()
        self.access_token_encrypted = f.encrypt(access_token.encode("utf-8"))
        if refresh_token is not None:
            self.refresh_token_encrypted = f.encrypt(refresh_token.encode("utf-8"))
        self.token_type = token_type or "Bearer"
        self.expires_at = (
            timezone.now() + timedelta(seconds=expires_in)
            if expires_in
            else None
        )
        self.scopes = scopes or ""
        self.last_refreshed_at = timezone.now()
        self.last_error = ""

    def tokens(self) -> tuple[str | None, str | None]:
        """Return ``(access_token, refresh_token)`` decrypted, or
        ``(None, None)`` when no token is stored."""
        if not self.access_token_encrypted:
            return None, None
        f = self._fernet()
        access = f.decrypt(bytes(self.access_token_encrypted)).decode("utf-8")
        refresh = (
            f.decrypt(bytes(self.refresh_token_encrypted)).decode("utf-8")
            if self.refresh_token_encrypted
            else None
        )
        return access, refresh

    def clear(self) -> None:
        self.access_token_encrypted = b""
        self.refresh_token_encrypted = b""
        self.expires_at = None
        self.scopes = ""
        self.account_email = ""
        self.account_subject = ""
        self.last_refreshed_at = None

    @property
    def is_connected(self) -> bool:
        return bool(self.access_token_encrypted)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return self.expires_at <= timezone.now()

    # ------------------------------------------------------------------
    @classmethod
    def current(cls) -> "OpenAITokenStore | None":
        """Return the singleton row if it exists, else None. Doesn't create."""
        return cls.objects.order_by("id").first()

    @classmethod
    def get_or_create_singleton(cls) -> "OpenAITokenStore":
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class OAuthAuthorizationFlow(BaseModel):
    """Short-lived scratchpad for one in-flight OAuth authorization.

    Created when superuser clicks "connect"; consumed by the OAuth callback
    when OpenAI redirects back. ``state`` is what we send to OpenAI as CSRF
    token; ``code_verifier`` is the PKCE secret kept server-side. Auto-
    expires after :data:`STATE_TTL_SECONDS` so we don't accumulate dead
    rows; ``cleanup_expired`` is best-effort GC."""

    STATE_TTL_SECONDS = 600  # 10 minutes is plenty for an OAuth dance.

    state = models.CharField(max_length=128, unique=True, db_index=True)
    code_verifier = models.CharField(max_length=256)
    redirect_uri = models.CharField(max_length=512)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_oauth_flows",
    )
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"OAuthFlow(state={self.state[:8]}…, by={self.initiated_by_id})"

    @classmethod
    def new(
        cls,
        *,
        user,
        redirect_uri: str,
        code_verifier: str,
    ) -> "OAuthAuthorizationFlow":
        return cls.objects.create(
            state=secrets.token_urlsafe(48),
            code_verifier=code_verifier,
            redirect_uri=redirect_uri,
            initiated_by=user,
            expires_at=timezone.now() + timedelta(seconds=cls.STATE_TTL_SECONDS),
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @classmethod
    def cleanup_expired(cls) -> int:
        """Delete rows past TTL. Best-effort; called from the callback view
        so we don't need a periodic Celery task for this."""
        cutoff = timezone.now() - timedelta(seconds=cls.STATE_TTL_SECONDS)
        n, _ = cls.objects.filter(expires_at__lt=cutoff).delete()
        return n


class AgentConversation(TenantAwareBaseModel):
    """A chat thread between one user and the agent inside one tenant.

    Privacy contract: ``(user, company)`` scopes the row. The list/detail
    endpoints filter on both, so a user switching tenants in the same
    browser session sees a different set of threads.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_conversations",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    is_archived = models.BooleanField(default=False, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "user", "-updated_at"]),
            models.Index(fields=["company", "user", "is_archived"]),
        ]

    def __str__(self):
        return f"AgentConversation(id={self.id}, user={self.user_id}, company={self.company_id})"


class AgentMessage(TenantAwareBaseModel):
    """One message inside an :class:`AgentConversation`.

    Roles map to OpenAI's chat-completion roles. ``tool_calls`` and
    ``tool_call_id`` are optional sidecars for function-calling — when the
    LLM requests a tool, that's an ``assistant`` row with ``tool_calls``
    populated; the result is a ``tool`` row with ``tool_call_id`` set."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_TOOL = "tool"
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_TOOL, "Tool"),
        (ROLE_SYSTEM, "System"),
    ]

    conversation = models.ForeignKey(
        AgentConversation,
        related_name="messages",
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, db_index=True)
    content = models.TextField(blank=True, default="")

    # Function-calling: assistant requests, tool returns
    tool_calls = models.JSONField(default=list, blank=True)
    tool_call_id = models.CharField(max_length=128, blank=True, default="")
    tool_name = models.CharField(max_length=128, blank=True, default="")

    # Token usage + model snapshot for cost/audit; populated only on
    # assistant messages.
    model_used = models.CharField(max_length=64, blank=True, default="")
    prompt_tokens = models.IntegerField(null=True, blank=True)
    completion_tokens = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["company", "role"]),
        ]
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"AgentMessage(id={self.id}, role={self.role}, conv={self.conversation_id})"
