"""
ERP integration pipeline models.

- ERPProvider: supported ERPs (Omie, etc.).
- ERPConnection: per-company credentials (app_key, app_secret).
- ERPAPIDefinition: API call + url, method, param schema (defaults from schema).
"""

from django.db import models

from multitenancy.models import BaseModel, TenantAwareBaseModel


class ERPProvider(BaseModel):
    """ERP system (Omie, etc.)."""

    slug = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    base_url = models.URLField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class ERPConnection(TenantAwareBaseModel):
    """Per-company ERP credentials (app_key, app_secret)."""

    provider = models.ForeignKey(
        ERPProvider,
        on_delete=models.CASCADE,
        related_name="connections",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Optional label for this connection (e.g. 'Production Omie').",
    )
    app_key = models.CharField(max_length=128)
    app_secret = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        label = self.name or f"{self.provider} @ {self.company}"
        return f"{label} (company={self.company_id})"

    class Meta:
        unique_together = ("company", "provider")
        ordering = ["company", "provider"]


class ERPAPIDefinition(BaseModel):
    """
    API call + param schema from API documentation.

    Stores the main APIs available and the parameters used (e.g. lcpListarRequest
    for ListarContasPagar). param_schema documents each field (name, type,
    description, required, default). Default payload is built from param_schema
    defaults.

    Phase-1 metadata (Sandbox API plan):
        * ``source``: where this definition came from (manual / imported /
          discovered via the Phase-2 URL discovery service).
        * ``version``: incremented on each save through the new structured
          API; lets the UI show a small history and a rollback button.
        * ``documentation_url``: the page that produced the definition (if
          discovered) or a reference link the operator pinned.
        * ``last_tested_at`` / ``last_test_outcome``: last time the
          ``test-call`` endpoint hit this definition. Surfaced in the
          listing as a "saúde" indicator so operators see at a glance which
          definitions are stale or broken.
        * ``auth_strategy``: how the request authenticates. Defaults to
          ``provider_default`` (current behaviour: app_key / app_secret in
          payload as Omie expects). Other strategies plug in different
          builders so we can support APIs outside Omie without forking the
          executor.
        * ``pagination_spec``: structured pagination config that replaces
          the hard-coded paging in ``omie_sync_service``. Optional during
          rollout; ``None`` keeps current behaviour.
        * ``records_path``: JMESPath expression telling the executor where
          to find the array of items in the response. Optional; falls
          back to the existing transform_engine extraction.
    """

    SOURCE_MANUAL = "manual"
    SOURCE_IMPORTED = "imported"
    SOURCE_DISCOVERED = "discovered"
    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Criada manualmente"),
        (SOURCE_IMPORTED, "Importada de arquivo"),
        (SOURCE_DISCOVERED, "Descoberta via URL"),
    ]

    OUTCOME_UNKNOWN = ""
    OUTCOME_SUCCESS = "success"
    OUTCOME_ERROR = "error"
    OUTCOME_AUTH_FAIL = "auth_fail"
    OUTCOME_CHOICES = [
        (OUTCOME_UNKNOWN, "—"),
        (OUTCOME_SUCCESS, "Sucesso"),
        (OUTCOME_ERROR, "Erro"),
        (OUTCOME_AUTH_FAIL, "Falha de autenticação"),
    ]

    AUTH_PROVIDER_DEFAULT = "provider_default"
    AUTH_QUERY_PARAMS = "query_params"
    AUTH_BEARER_HEADER = "bearer_header"
    AUTH_BASIC = "basic"
    AUTH_CUSTOM_TEMPLATE = "custom_template"
    AUTH_CHOICES = [
        (AUTH_PROVIDER_DEFAULT, "Padrão do provedor"),
        (AUTH_QUERY_PARAMS, "Query params"),
        (AUTH_BEARER_HEADER, "Bearer (Authorization header)"),
        (AUTH_BASIC, "Basic auth"),
        (AUTH_CUSTOM_TEMPLATE, "Template customizado"),
    ]

    provider = models.ForeignKey(
        ERPProvider,
        on_delete=models.CASCADE,
        related_name="api_definitions",
    )
    call = models.CharField(
        max_length=128,
        help_text="API method name (e.g. ListarContasPagar).",
    )
    url = models.URLField(
        max_length=512,
        help_text="Full URL for this API endpoint.",
    )
    method = models.CharField(
        max_length=10,
        default="POST",
        help_text="HTTP method (e.g. POST, GET).",
    )
    param_schema = models.JSONField(
        default=list,
        blank=True,
        help_text="List of param specs: [{name, type, description, required, default}, ...].",
    )
    description = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    transform_config = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text="Transform config spec: records extraction, explode rules, derived dates. See docs.",
    )
    unique_id_config = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "How to derive a stable id per item for dedup within this api_call: "
            "mode single_path with path, or mode composite with paths + optional separator; "
            "on_duplicate: update | flag | add."
        ),
    )

    # Phase-1 metadata fields. All optional / nullable to keep the
    # migration purely additive — every existing definition continues
    # to work without touching them.
    version = models.PositiveIntegerField(
        default=1,
        help_text="Bumped on each save through the structured editor.",
    )
    source = models.CharField(
        max_length=16,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        help_text="Where this definition came from.",
    )
    documentation_url = models.URLField(
        max_length=512,
        blank=True,
        null=True,
        help_text="Link to the API's official documentation page.",
    )
    last_tested_at = models.DateTimeField(blank=True, null=True)
    last_test_outcome = models.CharField(
        max_length=16,
        choices=OUTCOME_CHOICES,
        blank=True,
        default=OUTCOME_UNKNOWN,
    )
    last_test_error = models.TextField(
        blank=True,
        default="",
        help_text="Most recent test-call error message (if any).",
    )
    auth_strategy = models.CharField(
        max_length=24,
        choices=AUTH_CHOICES,
        default=AUTH_PROVIDER_DEFAULT,
        help_text="How requests against this definition are authenticated.",
    )
    pagination_spec = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Structured pagination config. Schema: "
            "{mode: 'none'|'page_number'|'cursor'|'offset', page_param, "
            "page_size_param, page_size, cursor_path, next_cursor_param, "
            "max_pages}. None keeps the hard-coded behaviour from "
            "omie_sync_service."
        ),
    )
    records_path = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "JMESPath expression to the array of items in the response. "
            "Optional: falls back to transform_engine extraction when blank."
        ),
    )

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.transform_engine import (
            validate_transform_config,
            validate_unique_id_config,
        )

        super().clean()
        if self.transform_config:
            errors = validate_transform_config(self.transform_config)
            if errors:
                raise ValidationError(
                    {
                        "transform_config": [f"{e.get('field', 'config')}: {e.get('message', '')}" for e in errors]
                    }
                )
        if self.unique_id_config:
            errors = validate_unique_id_config(self.unique_id_config)
            if errors:
                raise ValidationError(
                    {
                        "unique_id_config": [f"{e.get('field', 'config')}: {e.get('message', '')}" for e in errors]
                    }
                )
        if self.pagination_spec:
            from .services.api_definition_service import validate_pagination_spec
            errors = validate_pagination_spec(self.pagination_spec)
            if errors:
                raise ValidationError({"pagination_spec": errors})

    def __str__(self):
        return f"{self.provider.slug} / {self.call} (v{self.version})"

    class Meta:
        unique_together = ("provider", "call")
        ordering = ["provider", "call"]


class ErpApiEtlMapping(TenantAwareBaseModel):
    """
    ETL mapping from ERP API JSON response to app models (same commit flow as Excel ETL).

    Maps a list in the API response (e.g. produto_servico_cadastro) to target model rows
    using field_mappings (API key -> model field). Output is fed into execute_import_job()
    so substitution, validation, and commit behave like the Excel import.
    """

    name = models.CharField(max_length=100, help_text="e.g. Omie Produtos")
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    description = models.TextField(blank=True, null=True)

    # Source: which key in the API response holds the list of items
    response_list_key = models.CharField(
        max_length=120,
        help_text="JSON key containing the array of records (e.g. produto_servico_cadastro)",
    )

    # Target model (same names as in multitenancy.tasks.MODEL_APP_MAP)
    target_model = models.CharField(
        max_length=100,
        help_text="Target model: ProductService, ProductServiceCategory, etc.",
    )

    # Map API field names (exact key in each item) -> model field names
    field_mappings = models.JSONField(
        default=dict,
        help_text="""
        Map API keys to model fields. Format: {"api_key": "model_field"}
        Use __row_id for the row token (e.g. codigo -> __row_id for products).
        Nested keys use dot notation: "dadosIbpt.aliqFederal" -> "some_field"
        """,
    )

    # Static defaults for model fields not coming from API
    default_values = models.JSONField(
        default=dict,
        blank=True,
        help_text='Default values, e.g. {"item_type": "product", "track_inventory": false}',
    )

    # API key whose value is used as __row_id (for token resolution). If blank, look for "__row_id" in field_mappings.
    row_id_api_key = models.CharField(
        max_length=80,
        blank=True,
        help_text="API key whose value is used as __row_id (e.g. codigo). Same key can still map to a model field.",
    )

    # Optional: emit a category sheet first (MPTT). Keys in same item used to build category rows.
    category_from_same_response = models.BooleanField(
        default=False,
        help_text="If True, unique category keys are emitted as ProductServiceCategory rows first.",
    )
    category_name_key = models.CharField(
        max_length=80,
        blank=True,
        help_text="API key for category name (e.g. descricao_familia)",
    )
    category_id_key = models.CharField(
        max_length=80,
        blank=True,
        help_text="API key for stable category id (e.g. codigo_familia). Used for __row_id.",
    )
    category_target_model = models.CharField(
        max_length=100,
        blank=True,
        default="ProductServiceCategory",
        help_text="Model for category rows.",
    )
    category_fk_field = models.CharField(
        max_length=60,
        blank=True,
        default="category_fk",
        help_text="Target model FK field pointing to category (e.g. category_fk).",
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "ERP API ETL Mapping"
        indexes = [
            models.Index(fields=["company", "response_list_key"]),
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["company", "erp_id"]),
        ]

    def __str__(self):
        return f"{self.name}: {self.response_list_key} → {self.target_model}"


class ERPSyncJob(TenantAwareBaseModel):
    """Scheduled or manual sync job: fetches from Omie API and stores raw records."""

    connection = models.ForeignKey(
        ERPConnection,
        on_delete=models.CASCADE,
        related_name="sync_jobs",
    )
    api_definition = models.ForeignKey(
        ERPAPIDefinition,
        on_delete=models.CASCADE,
        related_name="sync_jobs",
    )
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    schedule_rrule = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="iCal RRULE for periodic runs (e.g. FREQ=HOURLY;INTERVAL=6)",
    )
    extra_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Override params for this job (e.g. pagina, registros_por_pagina)",
    )
    fetch_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Static/variable fetch rules: mode, static_params, date_dimension, bounds, cursor. See erp_integrations.services.fetch_config.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=20,
        choices=[
            ("never", "Never"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("partial", "Partial"),
            ("running", "Running"),
        ],
        default="never",
    )
    last_sync_record_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]
        verbose_name = "ERP Sync Job"

    def __str__(self):
        return f"{self.name} ({self.api_definition.call})"

    def clean(self):
        from django.core.exceptions import ValidationError

        from erp_integrations.services.fetch_config import validate_fetch_config

        super().clean()
        errs = validate_fetch_config(self.fetch_config or {})
        if errs:
            raise ValidationError({"fetch_config": errs})


class ERPSyncRun(TenantAwareBaseModel):
    """Audit log for each execution of an ERPSyncJob."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ]

    job = models.ForeignKey(
        ERPSyncJob,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    celery_task_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    pages_fetched = models.IntegerField(default=0)
    total_pages = models.IntegerField(null=True, blank=True)
    records_extracted = models.IntegerField(default=0)
    records_stored = models.IntegerField(default=0)
    records_skipped = models.IntegerField(
        default=0,
        help_text="Items skipped on sync (unchanged hash when on_duplicate=update).",
    )
    records_updated = models.IntegerField(
        default=0,
        help_text="Existing raw rows updated when on_duplicate=update.",
    )
    errors = models.JSONField(default=list)
    diagnostics = models.JSONField(
        default=dict,
        help_text="Picked path, timing, retries, etc.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    request_payload_redacted = models.JSONField(
        null=True,
        blank=True,
        help_text="Request payload with app_key/app_secret masked",
    )
    segments_total = models.IntegerField(
        default=0,
        help_text="Total segments planned for this run.",
    )
    segments_completed = models.IntegerField(
        default=0,
        help_text="Segments successfully completed before stopping.",
    )
    failed_segment_label = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Label of the segment that failed (e.g. '2026-03-16..2026-03-16').",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["job", "-started_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"Sync run #{self.id} [{self.status}] @ {self.started_at}"


class ERPRawRecord(models.Model):
    """
    Stores individual raw JSON records extracted from Omie API responses.
    Includes pagination header metadata from the page the record came from.
    """

    company = models.ForeignKey(
        "multitenancy.Company",
        on_delete=models.CASCADE,
        related_name="erp_raw_records",
    )
    sync_run = models.ForeignKey(
        ERPSyncRun,
        on_delete=models.CASCADE,
        related_name="records",
        null=True,
        blank=True,
        help_text="Set when record came from a single-job sync. Null when from a pipeline run.",
    )
    pipeline_run = models.ForeignKey(
        "erp_integrations.ERPSyncPipelineRun",
        on_delete=models.CASCADE,
        related_name="records",
        null=True,
        blank=True,
        help_text="Set when record came from a pipeline execution.",
    )
    pipeline_step_order = models.IntegerField(
        null=True,
        blank=True,
        help_text="Order (1-based) of the pipeline step that produced this record.",
    )
    api_call = models.CharField(max_length=128, db_index=True)

    # Record position
    page_number = models.IntegerField()
    record_index = models.IntegerField()
    global_index = models.IntegerField()

    # Pagination header from the page response
    page_records_count = models.IntegerField()
    total_pages = models.IntegerField()
    total_records = models.IntegerField()
    page_response_header = models.JSONField(
        default=dict,
        help_text="All top-level keys from the page response except the records array",
    )

    # Record data
    data = models.JSONField()
    record_hash = models.CharField(max_length=64, db_index=True)
    external_id = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable id extracted from item (single path or composite); scoped with api_call for lookups.",
    )
    is_duplicate = models.BooleanField(
        default=False,
        help_text="True when created with on_duplicate=flag and same external_id already existed.",
    )
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "api_call", "-fetched_at"]),
            models.Index(fields=["sync_run", "page_number", "record_index"]),
            models.Index(fields=["sync_run", "global_index"]),
            models.Index(fields=["record_hash"]),
            models.Index(fields=["company", "api_call", "external_id"]),
            models.Index(fields=["pipeline_run", "pipeline_step_order"]),
        ]

    def __str__(self):
        return f"Record {self.global_index} (page {self.page_number}, idx {self.record_index})"


class ERPSyncPipeline(TenantAwareBaseModel):
    """
    Composite sync definition: ordered sequence of API calls whose outputs may
    feed later steps' params. Parallels ERPSyncJob for registration/management;
    does not replace it.
    """

    connection = models.ForeignKey(
        ERPConnection,
        on_delete=models.CASCADE,
        related_name="sync_pipelines",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    schedule_rrule = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="iCal RRULE for periodic runs (e.g. FREQ=HOURLY;INTERVAL=6).",
    )
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        max_length=20,
        choices=[
            ("never", "Never"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("partial", "Partial"),
            ("running", "Running"),
        ],
        default="never",
    )
    last_run_record_count = models.IntegerField(default=0)

    # Phase-4: scheduled routines.
    is_paused = models.BooleanField(
        default=False,
        help_text="When true, the scheduler skips this pipeline. Distinct from is_active so an operator can pause without losing the agendamento.",
    )
    incremental_config = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Schema: {field, operator, param_name, format, lookback_seconds}. "
            "Tells the scheduler how to inject a 'changed since X' filter on "
            "the first step. Optional — pipelines without it run full-dump."
        ),
    )
    last_high_watermark = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Latest 'change date' the scheduler successfully imported. The next scheduled run uses (this - lookback_seconds) as the from-date.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "ERP Sync Pipeline"

    def __str__(self):
        return f"{self.name} (pipeline)"


class ERPSyncPipelineStep(BaseModel):
    """
    One ordered step in a pipeline. Each step = one ERPAPIDefinition call,
    with optional extra_params (static) and param_bindings (from prior steps).

    param_bindings shape (JSON list):
      [
        {"mode": "static",   "into": "codigo_cliente", "value": 42},
        {"mode": "jmespath", "source_step": 1, "expression": "clientes[0].codigo", "into": "codigo_cliente"},
        {"mode": "fanout",   "source_step": 1, "expression": "clientes[*].codigo", "into": "codigo_cliente"}
      ]

    - "static": constant value merged into param_overrides.
    - "jmespath": evaluates expression against step context, single value.
    - "fanout": evaluates to a list; step runs once per value (only one fanout
      binding allowed per step in v1).
    """

    pipeline = models.ForeignKey(
        ERPSyncPipeline,
        on_delete=models.CASCADE,
        related_name="steps",
    )
    order = models.PositiveIntegerField(
        help_text="1-based execution order within the pipeline.",
    )
    api_definition = models.ForeignKey(
        ERPAPIDefinition,
        on_delete=models.PROTECT,
        related_name="pipeline_steps",
    )
    extra_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Static param overrides for this step (merged before bindings).",
    )
    param_bindings = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered list of bindings that derive params from prior step outputs. See docstring.",
    )
    select_fields = models.JSONField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Optional JMESPath expression for preview projection (sandbox/dry_run). "
            "Does not affect stored ERPRawRecord.data."
        ),
    )

    class Meta:
        ordering = ["pipeline", "order"]
        unique_together = ("pipeline", "order")
        verbose_name = "ERP Sync Pipeline Step"

    def __str__(self):
        return f"{self.pipeline.name} #{self.order} -> {self.api_definition.call}"


class ERPSyncPipelineRun(TenantAwareBaseModel):
    """Audit log for one execution of an ERPSyncPipeline."""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("partial", "Partial"),
    ]

    pipeline = models.ForeignKey(
        ERPSyncPipeline,
        on_delete=models.CASCADE,
        related_name="runs",
        null=True,
        blank=True,
        help_text="Null for ad-hoc sandbox executions with no persisted pipeline.",
    )
    celery_task_id = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    records_extracted = models.IntegerField(default=0)
    records_stored = models.IntegerField(default=0)
    records_skipped = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    errors = models.JSONField(default=list)
    diagnostics = models.JSONField(
        default=dict,
        help_text="Per-step diagnostics, bindings resolved, fanout counts, retries, etc.",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    failed_step_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Order (1-based) of the step that failed, if any.",
    )
    is_sandbox = models.BooleanField(
        default=False,
        help_text="True for ad-hoc sandbox runs (preview-only, not persisted raw records).",
    )

    # Phase-4: scheduled run telemetry.
    TRIGGERED_BY_CHOICES = [
        ("schedule", "Scheduled (Celery beat)"),
        ("manual", "Manual (UI)"),
        ("api", "API (programmatic)"),
        ("sandbox", "Sandbox preview"),
    ]
    triggered_by = models.CharField(
        max_length=16,
        choices=TRIGGERED_BY_CHOICES,
        default="manual",
        help_text="Which surface fired this run.",
    )
    incremental_window_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Start of the incremental window the scheduler used (if any).",
    )
    incremental_window_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of the incremental window the scheduler used (if any).",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["pipeline", "-started_at"]),
            models.Index(fields=["status"]),
        ]
        verbose_name = "ERP Sync Pipeline Run"

    def __str__(self):
        label = self.pipeline.name if self.pipeline else "sandbox"
        return f"Pipeline run #{self.id} [{self.status}] ({label})"
