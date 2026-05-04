from rest_framework import serializers

from .models import (
    ERPAPIDefinition,
    ERPConnection,
    ERPProvider,
    ERPRawRecord,
    ERPSyncJob,
    ERPSyncPipeline,
    ERPSyncPipelineRun,
    ERPSyncPipelineStep,
    ERPSyncRun,
)
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
    """Joined provider + API definition: url, method, param_schema, payload (defaults from schema).

    Phase-1 fields exposed: version, source, documentation_url,
    last_tested_at, last_test_outcome, last_test_error, auth_strategy,
    pagination_spec, records_path. All optional / default-ed so the
    serializer is backward compatible with existing callers.
    """

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
            "transform_config",
            "unique_id_config",
            "description",
            "is_active",
            # Phase-1 metadata.
            "version",
            "source",
            "documentation_url",
            "last_tested_at",
            "last_test_outcome",
            "last_test_error",
            "auth_strategy",
            "pagination_spec",
            "records_path",
        ]
        read_only_fields = [
            "version",
            "last_tested_at",
            "last_test_outcome",
            "last_test_error",
        ]

    def get_payload(self, obj):
        return payload_from_param_schema(obj.param_schema or [])

    def validate_param_schema(self, value):
        from .services.api_definition_service import validate_param_schema
        errors = validate_param_schema(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate_pagination_spec(self, value):
        from .services.api_definition_service import validate_pagination_spec
        errors = validate_pagination_spec(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def update(self, instance, validated_data):
        # Bump version on every successful update through the structured
        # editor. Read-only fields (last_tested_*) are managed by the
        # /test-call action, not by save().
        instance = super().update(instance, validated_data)
        ERPAPIDefinition.objects.filter(pk=instance.pk).update(version=instance.version + 1)
        instance.refresh_from_db(fields=["version"])
        return instance


class APIDefinitionTestCallRequestSerializer(serializers.Serializer):
    """Body for ``POST /api-definitions/{id}/test-call/``.

    The connection supplies credentials; ``param_values`` overrides
    individual param defaults; ``max_pages`` caps the call so the
    operator can't accidentally pull a million rows from the editor.
    """

    connection_id = serializers.IntegerField()
    param_values = serializers.JSONField(required=False, default=dict)
    max_pages = serializers.IntegerField(required=False, default=1, min_value=1, max_value=5)


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
            "pipeline_run",
            "pipeline_step_order",
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


class ERPSyncPipelineStepSerializer(serializers.ModelSerializer):
    api_call = serializers.CharField(source="api_definition.call", read_only=True)

    class Meta:
        model = ERPSyncPipelineStep
        fields = [
            "id",
            "order",
            "api_definition",
            "api_call",
            "extra_params",
            "param_bindings",
            "select_fields",
        ]


class ERPSyncPipelineSerializer(serializers.ModelSerializer):
    steps = ERPSyncPipelineStepSerializer(many=True, required=False)
    connection_name = serializers.CharField(source="connection.name", read_only=True)
    provider = serializers.IntegerField(source="connection.provider_id", read_only=True)

    class Meta:
        model = ERPSyncPipeline
        fields = [
            "id",
            "connection",
            "connection_name",
            "provider",
            "name",
            "description",
            "is_active",
            "schedule_rrule",
            "last_run_at",
            "last_run_status",
            "last_run_record_count",
            "steps",
            # Phase-4 metadata
            "is_paused",
            "incremental_config",
            "last_high_watermark",
        ]
        read_only_fields = [
            "last_run_at",
            "last_run_status",
            "last_run_record_count",
            "last_high_watermark",
        ]

    def _validate_step_payload(self, step_data, pipeline_provider_id):
        api_def = step_data.get("api_definition")
        api_def_id = getattr(api_def, "id", api_def)
        if api_def_id is None:
            raise serializers.ValidationError({"steps": "Each step requires api_definition."})
        if isinstance(api_def, ERPAPIDefinition):
            if api_def.provider_id != pipeline_provider_id:
                raise serializers.ValidationError(
                    {"steps": f"api_definition {api_def_id} provider does not match pipeline connection provider."}
                )

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        connection = validated_data.get("connection")
        if connection and "company" not in validated_data:
            validated_data["company"] = connection.company
        pipeline = super().create(validated_data)

        for i, step in enumerate(steps_data):
            self._validate_step_payload(step, connection.provider_id if connection else None)
            ERPSyncPipelineStep.objects.create(
                pipeline=pipeline,
                order=step.get("order") or (i + 1),
                api_definition=step["api_definition"],
                extra_params=step.get("extra_params") or {},
                param_bindings=step.get("param_bindings") or [],
                select_fields=step.get("select_fields"),
            )
        return pipeline

    def update(self, instance, validated_data):
        steps_data = validated_data.pop("steps", None)
        instance = super().update(instance, validated_data)

        if steps_data is not None:
            provider_id = instance.connection.provider_id if instance.connection_id else None
            instance.steps.all().delete()
            for i, step in enumerate(steps_data):
                self._validate_step_payload(step, provider_id)
                ERPSyncPipelineStep.objects.create(
                    pipeline=instance,
                    order=step.get("order") or (i + 1),
                    api_definition=step["api_definition"],
                    extra_params=step.get("extra_params") or {},
                    param_bindings=step.get("param_bindings") or [],
                    select_fields=step.get("select_fields"),
                )
        return instance


class ERPSyncPipelineRunSerializer(serializers.ModelSerializer):
    pipeline_name = serializers.CharField(source="pipeline.name", read_only=True)

    class Meta:
        model = ERPSyncPipelineRun
        fields = [
            "id",
            "pipeline",
            "pipeline_name",
            "celery_task_id",
            "status",
            "records_extracted",
            "records_stored",
            "records_skipped",
            "records_updated",
            "errors",
            "diagnostics",
            "started_at",
            "completed_at",
            "duration_seconds",
            "failed_step_order",
            "is_sandbox",
        ]


class _SandboxStepSerializer(serializers.Serializer):
    """Inline step spec for the sandbox endpoint."""

    order = serializers.IntegerField(required=False, min_value=1)
    api_definition_id = serializers.IntegerField()
    extra_params = serializers.JSONField(required=False, default=dict)
    param_bindings = serializers.JSONField(required=False, default=list)
    select_fields = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PipelineSandboxRequestSerializer(serializers.Serializer):
    connection_id = serializers.IntegerField()
    steps = _SandboxStepSerializer(many=True)
    max_steps = serializers.IntegerField(required=False, min_value=1, max_value=10)
    max_pages_per_step = serializers.IntegerField(required=False, min_value=1, max_value=5)
    max_fanout = serializers.IntegerField(required=False, min_value=1, max_value=200)
