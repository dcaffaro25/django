# -*- coding: utf-8 -*-
"""
Inventory core models: Warehouse, UoM, StockMovement, InventoryLayer, InventoryBalance.
"""
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError

from multitenancy.models import TenantAwareBaseModel


class Warehouse(TenantAwareBaseModel):
    """Warehouse or storage location (optional for single-location tenants)."""
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Warehouse"
        verbose_name_plural = "Warehouses"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"],
                name="inventory_warehouse_company_code_uniq",
            ),
        ]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class UnitOfMeasure(TenantAwareBaseModel):
    """Unit of measure (e.g. UN, KG, CX, M2)."""
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name = "Unit of Measure"
        verbose_name_plural = "Units of Measure"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"],
                name="inventory_uom_company_code_uniq",
            ),
        ]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} ({self.name})"


class UoMConversion(TenantAwareBaseModel):
    """
    Conversion between UoMs. factor: 1 from_uom = factor * to_uom.
    E.g. 1 CX = 12 UN -> from_uom=CX, to_uom=UN, factor=12.
    """
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="uom_conversions",
        help_text="Null = global conversion applicable to any product.",
    )
    from_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.CASCADE,
        related_name="conversions_from",
    )
    to_uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.CASCADE,
        related_name="conversions_to",
    )
    factor = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        help_text="1 from_uom = factor * to_uom",
    )

    class Meta:
        verbose_name = "UoM Conversion"
        verbose_name_plural = "UoM Conversions"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "product", "from_uom", "to_uom"],
                name="inventory_uomconv_company_product_from_to_uniq",
            ),
        ]

    def __str__(self):
        prod = self.product_id or "global"
        return f"{prod}: 1 {self.from_uom.code} = {self.factor} {self.to_uom.code}"


class StockMovement(TenantAwareBaseModel):
    """
    Immutable audit log of stock movements.
    Source: NF-e items, manual adjustments, inventory counts.
    """
    MOVEMENT_TYPES = [
        ("inbound", "Inbound"),
        ("outbound", "Outbound"),
        ("adjustment", "Adjustment"),
        ("return_in", "Return In"),
        ("return_out", "Return Out"),
    ]
    SOURCE_TYPES = [
        ("nfe_item", "NF-e Item"),
        ("manual_adjustment", "Manual Adjustment"),
        ("inventory_count", "Inventory Count"),
    ]

    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Acquisition cost for inbound; filled by costing for outbound.",
    )
    uom = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_date = models.DateTimeField(db_index=True)
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPES)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    nfe_item = models.ForeignKey(
        "billing.NotaFiscalItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    nota_fiscal = models.ForeignKey(
        "billing.NotaFiscal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    reference = models.CharField(max_length=200, blank=True)
    idempotency_key = models.CharField(
        max_length=200,
        db_index=True,
        help_text="Prevents duplicate ingestion (e.g. nfe_item:123).",
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                name="inventory_stockmovement_idempotency_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "movement_date"]),
            models.Index(fields=["warehouse", "movement_date"]),
            models.Index(fields=["movement_type"]),
        ]
        ordering = ["-movement_date", "-id"]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} {self.uom.code} {self.product.code} @ {self.movement_date}"

    def save(self, *args, **kwargs):
        if self.pk and not kwargs.get("force_save"):
            raise ValidationError("StockMovement records are immutable; updates not allowed.")
        if self.quantity <= 0:
            raise ValidationError("StockMovement quantity must be positive.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("StockMovement records cannot be deleted (audit trail).")


class InventoryLayer(TenantAwareBaseModel):
    """
    Cost layer (lot) created from inbound movements for FIFO/LIFO costing.
    Outbound movements consume layers according to strategy rules.
    """
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.PROTECT,
        related_name="inventory_layers",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventory_layers",
    )
    source_movement = models.ForeignKey(
        StockMovement,
        on_delete=models.PROTECT,
        related_name="created_layers",
        help_text="The inbound movement that created this layer.",
    )
    original_qty = models.DecimalField(max_digits=15, decimal_places=4)
    remaining_qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6)
    layer_date = models.DateTimeField(db_index=True)
    is_exhausted = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Inventory Layer"
        verbose_name_plural = "Inventory Layers"
        indexes = [
            models.Index(fields=["product", "warehouse", "layer_date"]),
            models.Index(fields=["is_exhausted"]),
        ]
        ordering = ["layer_date", "id"]

    def __str__(self):
        return f"Layer {self.id}: {self.remaining_qty} {self.product.code} @ {self.unit_cost}"


class InventoryBalance(TenantAwareBaseModel):
    """
    Denormalized on-hand balance per product/warehouse.
    Rebuildable from StockMovement; used for performance.
    """
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.CASCADE,
        related_name="inventory_balances",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="inventory_balances",
    )
    on_hand_qty = models.DecimalField(max_digits=15, decimal_places=4, default=Decimal("0"))
    last_movement_date = models.DateTimeField(null=True, blank=True)
    last_rebuilt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Inventory Balance"
        verbose_name_plural = "Inventory Balances"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "product", "warehouse"],
                name="inventory_balance_company_product_wh_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["product"]),
            models.Index(fields=["warehouse"]),
        ]

    def __str__(self):
        wh = self.warehouse.code if self.warehouse else "default"
        return f"{self.product.code} @ {wh}: {self.on_hand_qty}"


# Import costing and alert models so they are registered with Django
from .models_costing import (  # noqa: E402
    TenantCostingConfig,
    InventoryValuationSnapshot,
    CogsAllocation,
    AccountingImpact,
)
from .models_alerts import InventoryAlert  # noqa: E402
