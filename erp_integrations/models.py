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
        ]

    def __str__(self):
        return f"{self.name}: {self.response_list_key} → {self.target_model}"
