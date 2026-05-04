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

    Per-conversation knobs (``model``, ``reasoning_effort``,
    ``include_page_context``) override the global defaults. Empty / False
    means "fall back to system default" so changing the platform default
    immediately applies to threads that never opted into a specific value.
    """

    REASONING_EFFORT_CHOICES = [
        ("", "Default"),
        ("minimal", "Minimal"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_conversations",
    )
    title = models.CharField(max_length=255, blank=True, default="")
    is_archived = models.BooleanField(default=False, db_index=True)

    # Per-conversation overrides — empty = inherit from settings.
    model = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Codex model slug (e.g. gpt-5.5). Empty = OPENAI_DEFAULT_MODEL.",
    )
    reasoning_effort = models.CharField(
        max_length=16, blank=True, default="",
        choices=REASONING_EFFORT_CHOICES,
        help_text="Reasoning effort. Empty = no reasoning param sent.",
    )
    include_page_context = models.BooleanField(
        default=False,
        help_text="If True, the chat endpoint accepts a page_context blob and the runtime injects it into the system prompt.",
    )

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


class AgentPlaybook(TenantAwareBaseModel):
    """A saved configuration for a recurring agent action.

    First class of playbook: ``recon`` — saves the knobs for a
    ``run_reconciliation_agent`` invocation (auto-accept threshold,
    ambiguity gap, min confidence, scope filters) under a name the
    agent can recall later. The same row is intended to back an
    eventual scheduled-task surface (cron-driven monthly close, etc.).

    The action's parameters live in ``params`` as JSON so different
    playbook kinds can share one model without column proliferation.
    """

    KIND_RECON = "recon"
    KIND_CHOICES = [(KIND_RECON, "Reconciliation auto-accept")]

    name = models.CharField(max_length=80)
    kind = models.CharField(
        max_length=16, choices=KIND_CHOICES, default=KIND_RECON, db_index=True,
    )
    description = models.CharField(max_length=255, blank=True, default="")
    params = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Kind-specific params. For 'recon': "
            "auto_accept_threshold, ambiguity_gap, min_confidence, "
            "bank_account_id, date_from, date_to, limit."
        ),
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # Optional schedule expression — free-form for now; surfaced through a
    # follow-up scheduled-tasks integration. Not enforced at the model level.
    schedule_cron = models.CharField(max_length=64, blank=True, default="")

    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("company", "name")
        indexes = [
            models.Index(fields=["company", "kind", "is_active"]),
            models.Index(fields=["company", "-last_run_at"]),
        ]
        ordering = ["company", "kind", "name"]

    def __str__(self):
        return f"AgentPlaybook({self.kind}/{self.name}, company={self.company_id})"


class AgentMessageAttachment(TenantAwareBaseModel):
    """A file uploaded by the user inside an agent conversation — Phase 2.

    The agent runtime converts each attachment into the right input
    item for the LLM:

    * NF-e XML / NFCe XML  → parsed with the existing fiscal pipeline
      and surfaced as ``input_text`` containing the structured fields
      so the model doesn't need to read raw XML.
    * OFX                  → parsed with the existing OFX importer.
    * PDF / image          → wrapped as ``input_image`` so the Codex
      multimodal pipeline can OCR and understand layout.
    * Anything else        → ignored with a warning log; the agent is
      told the attachment couldn't be processed.

    ``extracted_text`` caches the parser/OCR output so re-asking about
    the same attachment doesn't re-process. Stored on a Railway Volume
    in production (``settings.MEDIA_ROOT`` mounted at the volume path).
    """

    KIND_NFE_XML = "nfe_xml"
    KIND_OFX = "ofx"
    KIND_PDF = "pdf"
    KIND_IMAGE = "image"
    KIND_OTHER = "other"
    KIND_CHOICES = [
        (KIND_NFE_XML, "NF-e / NFCe XML"),
        (KIND_OFX, "OFX bank statement"),
        (KIND_PDF, "PDF document"),
        (KIND_IMAGE, "Image (PNG/JPEG/etc.)"),
        (KIND_OTHER, "Other / unsupported"),
    ]

    message = models.ForeignKey(
        "AgentMessage",
        related_name="attachments",
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Null while the file is uploaded but not yet attached to a message.",
    )
    conversation = models.ForeignKey(
        "AgentConversation",
        related_name="attachments",
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to="agent/attachments/%Y/%m/")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_OTHER, db_index=True)
    extracted_text = models.TextField(
        blank=True, default="",
        help_text="Cached output of the parser/OCR step. Empty until ingest_document runs.",
    )
    extraction_error = models.CharField(max_length=400, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["company", "kind"]),
        ]
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"AgentMessageAttachment(id={self.id}, kind={self.kind}, conv={self.conversation_id})"


class AgentToolCallLog(TenantAwareBaseModel):
    """One row per tool invocation by the agent runtime — Phase 0 audit log.

    Captures *what happened* without storing full args/responses (PII risk).
    The redacted ``args_summary`` keeps the first ~200 chars of the JSON
    representation, which is enough to debug "what did the agent do at 14:32"
    without leaking customer data into observability tooling.

    Indexed for two main queries:
      * "what's the agent doing today?" → (company, -created_at)
      * "which tool errors recurrently?" → (tool_name, status, -created_at)
    """

    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_WARN = "warn"  # tool returned an {"error": ...} blob (handled)
    STATUS_REJECTED = "rejected"  # write blocked by policy
    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_ERROR, "Exception"),
        (STATUS_WARN, "Handled error"),
        (STATUS_REJECTED, "Rejected by policy"),
    ]

    conversation = models.ForeignKey(
        AgentConversation,
        related_name="tool_calls",
        on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Null for tool calls outside a chat conversation (raw MCP, mgmt cmd).",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="agent_tool_calls",
    )
    tool_name = models.CharField(max_length=128, db_index=True)
    tool_domain = models.CharField(
        max_length=32, blank=True, default="",
        help_text="Domain tag from the ToolDef (recon/fiscal/external/meta/erp/internal).",
    )
    args_summary = models.CharField(
        max_length=400, blank=True, default="",
        help_text="Truncated JSON of args; never store full args (PII).",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, db_index=True)
    error_type = models.CharField(max_length=128, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    latency_ms = models.IntegerField(null=True, blank=True)
    response_size_bytes = models.IntegerField(null=True, blank=True)
    iteration = models.IntegerField(
        null=True, blank=True,
        help_text="Which agent_runtime iteration this call belongs to (1..AGENT_MAX_TOOL_ITERATIONS).",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["tool_name", "status", "-created_at"]),
            models.Index(fields=["conversation", "-created_at"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"AgentToolCallLog({self.tool_name} {self.status} conv={self.conversation_id})"


class AgentWriteAudit(TenantAwareBaseModel):
    """One row per attempted write by the agent — Phase 1 confirmation pattern.

    Even before live writes are enabled, every dry_run goes through this
    table so the operator can see *what the agent would have done* before
    flipping the kill-switch. When live writes turn on, the same row gets
    promoted from dry_run=True to dry_run=False with the actual side
    effects recorded.

    ``before_state`` and ``after_state`` are JSON snapshots of the rows
    touched, capped at ~10KB each. Sufficient for "was the agent right?"
    review and for the eventual undo path (replay before_state).
    """

    STATUS_DRY_RUN = "dry_run"
    STATUS_PROPOSED = "proposed"   # awaiting user confirmation
    STATUS_APPLIED = "applied"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_UNDONE = "undone"
    STATUS_CHOICES = [
        (STATUS_DRY_RUN, "Dry-run only (no DB change)"),
        (STATUS_PROPOSED, "Awaiting user confirmation"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed during apply"),
        (STATUS_UNDONE, "Undone"),
    ]

    conversation = models.ForeignKey(
        AgentConversation,
        related_name="write_audits",
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="agent_write_audits",
    )
    tool_name = models.CharField(max_length=128, db_index=True)
    target_model = models.CharField(
        max_length=128, blank=True, default="",
        help_text="e.g. 'accounting.JournalEntry'",
    )
    target_ids = models.JSONField(
        default=list, blank=True,
        help_text="PKs touched by the write — empty list means 'creating new'.",
    )
    args_summary = models.CharField(max_length=400, blank=True, default="")
    before_state = models.JSONField(default=dict, blank=True)
    after_state = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, db_index=True)
    error_type = models.CharField(max_length=128, blank=True, default="")
    error_message = models.CharField(max_length=500, blank=True, default="")
    undo_token = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Random token the user can pass to undo_* tools to reverse this write.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["tool_name", "status", "-created_at"]),
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["target_model", "status"]),
        ]
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"AgentWriteAudit({self.tool_name} {self.status} ids={self.target_ids})"
