"""
Models for the new report engine.

Two tables — both tenant-scoped:

* :class:`ReportTemplate` — a canonical JSON document describing report
  structure. No secondary "line templates" table; the ``document`` JSONField
  is the source of truth. Pydantic validates on write (in the serializer).

* :class:`ReportInstance` — a saved ``/calculate/`` result. Stores the raw
  ``result`` JSON plus a ``template_snapshot`` (immutable copy of the
  template's document at generation time) so historical statements never
  drift when the template is later edited.

The legacy tables ``FinancialStatementTemplate``/``FinancialStatement`` etc.
in :mod:`accounting.models_financial_statements` are untouched.
"""

from django.db import models

from multitenancy.models import TenantAwareBaseModel


REPORT_TYPE_CHOICES = [
    ("balance_sheet", "Balance Sheet"),
    ("income_statement", "Income Statement (P&L)"),
    ("cash_flow", "Cash Flow Statement"),
    ("trial_balance", "Trial Balance"),
    ("general_ledger", "General Ledger"),
    ("custom", "Custom Report"),
]

INSTANCE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("final", "Final"),
    ("archived", "Archived"),
]


class ReportTemplate(TenantAwareBaseModel):
    """A report template identified by a canonical JSON document."""

    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)
    description = models.TextField(blank=True, null=True)
    document = models.JSONField(
        help_text="Canonical template document (validated by pydantic on write).",
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Default template for this report type within the tenant.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("company", "name")
        indexes = [
            models.Index(fields=["company", "report_type", "is_active"]),
            models.Index(fields=["company", "is_default"]),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:  # pragma: no cover — debug only
        return f"{self.name} ({self.report_type})"


class ReportInstance(TenantAwareBaseModel):
    """A persisted ``/calculate/`` result with an immutable template snapshot."""

    template = models.ForeignKey(
        ReportTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instances",
        help_text="Soft reference — nulled if the template is deleted. "
                  "The authoritative structure lives in ``template_snapshot``.",
    )
    template_snapshot = models.JSONField(
        help_text="Frozen copy of the template document at generation time.",
    )
    name = models.CharField(max_length=200)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)
    periods = models.JSONField(
        help_text="The ``periods[]`` passed to /calculate/.",
    )
    result = models.JSONField(
        help_text="The /calculate/ response (lines × periods, memory, warnings).",
    )
    status = models.CharField(
        max_length=20,
        choices=INSTANCE_STATUS_CHOICES,
        default="draft",
    )
    generated_by = models.ForeignKey(
        "multitenancy.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_instances",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "report_type", "-generated_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["template", "-generated_at"]),
        ]
        ordering = ["-generated_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} [{self.status}] {self.generated_at:%Y-%m-%d}"
