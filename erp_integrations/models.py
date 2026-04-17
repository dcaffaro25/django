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
    """

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

    def __str__(self):
        return f"{self.provider.slug} / {self.call}"

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
        ]

    def __str__(self):
        return f"Record {self.global_index} (page {self.page_number}, idx {self.record_index})"
