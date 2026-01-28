from django.contrib import admin

from .models import ERPAPIDefinition, ERPConnection, ERPProvider


@admin.register(ERPProvider)
class ERPProviderAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "base_url", "is_active")
    list_filter = ("is_active",)
    search_fields = ("slug", "name")


@admin.register(ERPConnection)
class ERPConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "company", "app_key_masked", "is_active")
    list_filter = ("provider", "is_active", "company")
    search_fields = ("name", "app_key")
    raw_id_fields = ("company", "provider")

    def app_key_masked(self, obj):
        if not obj.app_key:
            return "-"
        if len(obj.app_key) <= 8:
            return "****"
        return obj.app_key[:4] + "…" + obj.app_key[-4:]

    app_key_masked.short_description = "App key"


@admin.register(ERPAPIDefinition)
class ERPAPIDefinitionAdmin(admin.ModelAdmin):
    list_display = ("call", "provider", "description", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("call", "description")
