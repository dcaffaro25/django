"""
ERP integration pipeline models.

- ERPProvider: supported ERPs (Omie, etc.).
- ERPConnection: per-company credentials (app_key, app_secret).
- ERPAPIDefinition: API call name + param schema/defaults from API docs.
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
    for ListarContasPagar). default_param holds the default param object;
    param_schema documents each field (name, type, description, required).
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
    param_schema = models.JSONField(
        default=list,
        blank=True,
        help_text="List of param specs: [{name, type, description, required, default}, ...].",
    )
    default_param = models.JSONField(
        default=dict,
        blank=True,
        help_text="Default param object used when building the request.",
    )
    description = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.provider.slug} / {self.call}"

    class Meta:
        unique_together = ("provider", "call")
        ordering = ["provider", "call"]
