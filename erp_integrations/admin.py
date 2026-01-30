from django.contrib import admin

from .models import ERPAPIDefinition, ERPConnection, ErpApiEtlMapping, ERPProvider


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
    list_display = ("call", "provider", "url", "method", "description", "is_active")
    list_filter = ("provider", "is_active")
    search_fields = ("call", "description", "url")


@admin.register(ErpApiEtlMapping)
class ErpApiEtlMappingAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "response_list_key", "target_model", "category_from_same_response", "is_active")
    list_filter = ("is_active", "category_from_same_response", "target_model")
    search_fields = ("name", "response_list_key", "target_model")
    raw_id_fields = ("company",)
    readonly_fields = ()
    fieldsets = (
        (None, {"fields": ("name", "description", "company", "is_active")}),
        ("Source", {"fields": ("response_list_key",)}),
        ("Target", {"fields": ("target_model", "field_mappings", "default_values", "row_id_api_key")}),
        (
            "Category (optional)",
            {
                "fields": (
                    "category_from_same_response",
                    "category_name_key",
                    "category_id_key",
                    "category_target_model",
                    "category_fk_field",
                )
            },
        ),
    )
