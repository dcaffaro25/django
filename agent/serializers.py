"""DRF serializers for the agent endpoints.

Two surfaces:

* :class:`OpenAIConnectionStatusSerializer` — what the admin page reads to
  render "Connected as X, expires in Y, last error Z". Never exposes the
  encrypted tokens themselves.
* :class:`AgentConversationSerializer` / :class:`AgentMessageSerializer` —
  chat history scoped to (user, company).
"""
from __future__ import annotations

from rest_framework import serializers

from .models import AgentConversation, AgentMessage, OpenAITokenStore


class OpenAIConnectionStatusSerializer(serializers.ModelSerializer):
    is_connected = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    connected_by_username = serializers.SerializerMethodField()

    class Meta:
        model = OpenAITokenStore
        fields = [
            "is_connected",
            "is_expired",
            "account_email",
            "account_subject",
            "chatgpt_account_id",
            "scopes",
            "connected_by_username",
            "connected_at",
            "last_refreshed_at",
            "expires_at",
            "last_error",
        ]

    def get_connected_by_username(self, obj):
        if obj.connected_by_id is None:
            return None
        return getattr(obj.connected_by, "username", None)


class AgentMessageAttachmentSerializer(serializers.ModelSerializer):
    """Compact attachment view returned alongside a message — Phase 2.

    No file URL is exposed; the agent operates on attachments by ID
    (via ``ingest_document``) and the chat widget only needs filename
    + kind + size + an optional ``summary`` line derived from the
    cached parser output (e.g. "NF 41651/1 · R$ 173,45 · MAGALU")."""

    summary = serializers.SerializerMethodField()

    class Meta:
        from .models import AgentMessageAttachment
        model = AgentMessageAttachment
        fields = [
            "id", "kind", "filename", "content_type", "size_bytes",
            "created_at", "summary",
        ]
        read_only_fields = fields

    def get_summary(self, obj) -> str:
        """One-line summary derived from the cached ``extracted_text``.

        Returns "" until ``ingest_document`` has run on the attachment.
        Each kind has a different shape — this peels the first
        meaningful line and drops the verbose tail.
        """
        from .models import AgentMessageAttachment
        text = (obj.extracted_text or "").strip()
        if not text:
            return ""
        if obj.kind == AgentMessageAttachment.KIND_NFE_XML:
            # First three lines of _ingest_nfe_xml's text are:
            # NF-e <num>/<serie>
            # Chave: ...
            # Emissão: ...
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            head = lines[0] if lines else ""
            valor = next(
                (l for l in lines if l.lower().startswith("valor total:")), "",
            ).replace("Valor total:", "").strip()
            dest = next(
                (l for l in lines if l.lower().startswith("destinatário:")), "",
            ).replace("Destinatário:", "").strip()
            # Truncate counterparty after the corporate name (drop CNPJ).
            dest_short = dest.split(" (")[0][:40]
            parts = [head]
            if valor:
                parts.append(valor)
            if dest_short:
                parts.append(dest_short)
            return " · ".join(parts)
        if obj.kind == AgentMessageAttachment.KIND_OFX:
            # First line: "OFX com N extrato(s):"
            first = text.splitlines()[0] if text else ""
            return first.strip()
        return ""


class AgentMessageSerializer(serializers.ModelSerializer):
    attachments = AgentMessageAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = AgentMessage
        fields = [
            "id",
            "role",
            "content",
            "tool_calls",
            "tool_call_id",
            "tool_name",
            "model_used",
            "prompt_tokens",
            "completion_tokens",
            "created_at",
            "attachments",
        ]
        read_only_fields = fields


class AgentConversationSerializer(serializers.ModelSerializer):
    last_message_at = serializers.DateTimeField(source="updated_at", read_only=True)
    message_count = serializers.SerializerMethodField()
    total_input_tokens = serializers.SerializerMethodField()
    total_output_tokens = serializers.SerializerMethodField()

    class Meta:
        model = AgentConversation
        fields = [
            "id",
            "title",
            "is_archived",
            "model",
            "reasoning_effort",
            "include_page_context",
            "created_at",
            "updated_at",
            "last_message_at",
            "message_count",
            "total_input_tokens",
            "total_output_tokens",
        ]
        read_only_fields = [
            "id", "created_at", "updated_at", "last_message_at",
            "message_count", "total_input_tokens", "total_output_tokens",
        ]

    def get_message_count(self, obj):
        return getattr(obj, "messages_count", obj.messages.count())

    def get_total_input_tokens(self, obj):
        agg = getattr(obj, "_token_totals", None)
        if agg is not None:
            return agg.get("prompt") or 0
        from django.db.models import Sum
        return obj.messages.aggregate(s=Sum("prompt_tokens"))["s"] or 0

    def get_total_output_tokens(self, obj):
        agg = getattr(obj, "_token_totals", None)
        if agg is not None:
            return agg.get("completion") or 0
        from django.db.models import Sum
        return obj.messages.aggregate(s=Sum("completion_tokens"))["s"] or 0


class AgentConversationDetailSerializer(AgentConversationSerializer):
    messages = AgentMessageSerializer(many=True, read_only=True)

    class Meta(AgentConversationSerializer.Meta):
        fields = AgentConversationSerializer.Meta.fields + ["messages"]
