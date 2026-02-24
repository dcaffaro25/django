# -*- coding: utf-8 -*-
"""
Inventory anomaly alerts: pack-vs-unit, price outliers, negative stock, etc.
"""
from django.conf import settings
from django.db import models

from multitenancy.models import TenantAwareBaseModel


class InventoryAlert(TenantAwareBaseModel):
    """
    Alert created by anomaly detection (pack-vs-unit, price outlier, etc.).
    Evidence fields support pack-vs-unit mismatch diagnosis.
    """
    ALERT_TYPES = [
        ("pack_vs_unit", "Pack vs Unit Mismatch"),
        ("price_outlier", "Price Outlier"),
        ("negative_stock", "Negative Stock"),
        ("stale_inventory", "Stale Inventory"),
    ]
    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("acknowledged", "Acknowledged"),
        ("resolved", "Resolved"),
        ("dismissed", "Dismissed"),
    ]

    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="warning")
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_alerts",
    )
    nfe_item = models.ForeignKey(
        "billing.NotaFiscalItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_alerts",
    )
    nota_fiscal = models.ForeignKey(
        "billing.NotaFiscal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_alerts",
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    evidence = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Expected unit price, observed unit price, deviation ratio, "
            "suspected conversion factor, historical reference window, reference items."
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_inventory_alerts",
    )

    class Meta:
        verbose_name = "Inventory Alert"
        verbose_name_plural = "Inventory Alerts"
        indexes = [
            models.Index(fields=["alert_type"]),
            models.Index(fields=["status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.alert_type}: {self.title}"
