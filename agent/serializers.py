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


class AgentMessageSerializer(serializers.ModelSerializer):
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
        ]
        read_only_fields = fields


class AgentConversationSerializer(serializers.ModelSerializer):
    last_message_at = serializers.DateTimeField(source="updated_at", read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = AgentConversation
        fields = [
            "id",
            "title",
            "is_archived",
            "created_at",
            "updated_at",
            "last_message_at",
            "message_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_message_at", "message_count"]

    def get_message_count(self, obj):
        # The viewset prefetches ``messages_count`` via ``annotate``; fall
        # back to a query when the annotation isn't there (admin / shell).
        return getattr(obj, "messages_count", obj.messages.count())


class AgentConversationDetailSerializer(AgentConversationSerializer):
    messages = AgentMessageSerializer(many=True, read_only=True)

    class Meta(AgentConversationSerializer.Meta):
        fields = AgentConversationSerializer.Meta.fields + ["messages"]
