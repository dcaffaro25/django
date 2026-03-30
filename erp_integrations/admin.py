from django.contrib import admin

from .models import (
    ERPAPIDefinition,
    ERPConnection,
    ErpApiEtlMapping,
    ERPProvider,
    ERPRawRecord,
    ERPSyncJob,
    ERPSyncRun,
)


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
    fieldsets = (
        (None, {"fields": ("provider", "call", "url", "method", "description", "is_active")}),
        ("Schema & transform", {"fields": ("param_schema", "transform_config", "unique_id_config")}),
        (
            "Audit",
            {
                "fields": ("created_by", "updated_by", "created_at", "updated_at", "is_deleted", "notes"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at")


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


@admin.register(ERPSyncJob)
class ERPSyncJobAdmin(admin.ModelAdmin):
    list_display = ("name", "connection", "api_definition", "is_active", "last_sync_status", "last_synced_at")
    list_filter = ("is_active", "last_sync_status")
    search_fields = ("name",)
    raw_id_fields = ("connection", "api_definition")
    fieldsets = (
        (None, {"fields": ("company", "connection", "api_definition", "name", "is_active")}),
        ("Schedule & params", {"fields": ("schedule_rrule", "extra_params", "fetch_config")}),
        ("Last sync", {"fields": ("last_synced_at", "last_sync_status", "last_sync_record_count")}),
    )


@admin.register(ERPSyncRun)
class ERPSyncRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "status",
        "pages_fetched",
        "records_stored",
        "records_skipped",
        "records_updated",
        "started_at",
    )
    list_filter = ("status",)
    readonly_fields = ("started_at", "completed_at", "duration_seconds", "diagnostics")
    raw_id_fields = ("job", "company")


@admin.register(ERPRawRecord)
class ERPRawRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sync_run",
        "api_call",
        "external_id",
        "is_duplicate",
        "page_number",
        "record_index",
        "global_index",
        "fetched_at",
    )
    list_filter = ("api_call", "is_duplicate")
    search_fields = ("record_hash", "external_id")
    raw_id_fields = ("sync_run", "company")
