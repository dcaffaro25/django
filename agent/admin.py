"""Django admin registrations for the agent app.

The token store is the only thing worth surfacing in /admin/ — encrypted
fields are hidden, decryption never happens here. Conversations are
tenant data; surface them in the per-tenant pages of the SPA, not the
platform-admin Django admin.
"""
from django.contrib import admin

from .models import OAuthAuthorizationFlow, OpenAITokenStore


@admin.register(OpenAITokenStore)
class OpenAITokenStoreAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account_email",
        "is_connected",
        "is_expired",
        "expires_at",
        "connected_by",
        "connected_at",
    )
    readonly_fields = (
        "access_token_encrypted",
        "refresh_token_encrypted",
        "token_type",
        "expires_at",
        "scopes",
        "account_email",
        "account_subject",
        "connected_by",
        "connected_at",
        "last_refreshed_at",
        "last_error",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Singleton — created via OAuth flow, never via admin form.
        return False


@admin.register(OAuthAuthorizationFlow)
class OAuthAuthorizationFlowAdmin(admin.ModelAdmin):
    list_display = ("id", "state_short", "initiated_by", "expires_at", "consumed_at")
    readonly_fields = (
        "state",
        "code_verifier",
        "redirect_uri",
        "initiated_by",
        "expires_at",
        "consumed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def state_short(self, obj):
        return f"{obj.state[:12]}…"
    state_short.short_description = "state"
