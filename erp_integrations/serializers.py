from rest_framework import serializers

from .models import ERPAPIDefinition, ERPConnection, ERPProvider, ERPRawRecord, ERPSyncJob, ERPSyncRun
from .services.payload_builder import payload_from_param_schema


class ERPProviderMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ERPProvider
        fields = ["id", "slug", "name", "base_url"]


class ERPConnectionSerializer(serializers.ModelSerializer):
    provider_display = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ERPConnection
        fields = [
            "id",
            "provider",
            "provider_display",
            "company",
            "name",
            "app_key",
            "app_secret",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "app_secret": {"write_only": True},
        }


class ERPConnectionListSerializer(serializers.ModelSerializer):
    """List view: mask app_key, never expose app_secret."""

    provider_display = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ERPConnection
        fields = [
            "id",
            "provider",
            "provider_display",
            "company",
            "name",
            "app_key_masked",
            "is_active",
        ]

    app_key_masked = serializers.SerializerMethodField()

    def get_app_key_masked(self, obj):
        if not obj.app_key:
            return ""
        if len(obj.app_key) <= 8:
            return "****"
        return obj.app_key[:4] + "…" + obj.app_key[-4:]


class ERPAPIDefinitionSerializer(serializers.ModelSerializer):
    """Joined provider + API definition: url, method, param_schema, payload (defaults from schema)."""

    provider_display = serializers.CharField(source="provider.name", read_only=True)
    payload = serializers.SerializerMethodField()

    class Meta:
        model = ERPAPIDefinition
        fields = [
            "id",
            "provider",
            "provider_display",
            "call",
            "url",
            "method",
            "param_schema",
            "payload",
            "unique_id_config",
            "description",
            "is_active",
        ]

    def get_payload(self, obj):
        return payload_from_param_schema(obj.param_schema or [])


class BuildPayloadRequestSerializer(serializers.Serializer):
    connection_id = serializers.IntegerField()
    api_definition_id = serializers.IntegerField()
    param_overrides = serializers.JSONField(required=False, default=dict)


class ErpEtlImportRequestSerializer(serializers.Serializer):
    """Request body for ERP API ETL import (preview or commit)."""

    mapping_id = serializers.IntegerField(help_text="ErpApiEtlMapping id for this company.")
    response = serializers.JSONField(help_text="Full API response dict (e.g. with produto_servico_cadastro).")
    commit = serializers.BooleanField(default=False, help_text="True to write to DB; False for preview only.")


class ERPSyncJobSerializer(serializers.ModelSerializer):
    api_call = serializers.CharField(source="api_definition.call", read_only=True)
    connection_name = serializers.CharField(source="connection.name", read_only=True)

    class Meta:
        model = ERPSyncJob
        fields = [
            "id",
            "connection",
            "connection_name",
            "api_definition",
            "api_call",
            "name",
            "is_active",
            "schedule_rrule",
            "extra_params",
            "fetch_config",
            "last_synced_at",
            "last_sync_status",
            "last_sync_record_count",
        ]

    def create(self, validated_data):
        connection = validated_data.get("connection")
        if connection and "company" not in validated_data:
            validated_data["company"] = connection.company
        return super().create(validated_data)


class ERPSyncRunSerializer(serializers.ModelSerializer):
    job_name = serializers.CharField(source="job.name", read_only=True)

    class Meta:
        model = ERPSyncRun
        fields = [
            "id",
            "job",
            "job_name",
            "celery_task_id",
            "status",
            "pages_fetched",
            "total_pages",
            "records_extracted",
            "records_stored",
            "records_skipped",
            "records_updated",
            "segments_total",
            "segments_completed",
            "failed_segment_label",
            "errors",
            "diagnostics",
            "started_at",
            "completed_at",
            "duration_seconds",
        ]


class ERPRawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = ERPRawRecord
        fields = [
            "id",
            "sync_run",
            "api_call",
            "page_number",
            "record_index",
            "global_index",
            "page_records_count",
            "total_pages",
            "total_records",
            "page_response_header",
            "data",
            "record_hash",
            "external_id",
            "is_duplicate",
            "fetched_at",
        ]
