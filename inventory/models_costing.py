# -*- coding: utf-8 -*-
"""
Costing strategy output models: config, valuation snapshots, COGS allocations, accounting impacts.
"""
from django.db import models

from multitenancy.models import TenantAwareBaseModel


class TenantCostingConfig(TenantAwareBaseModel):
    """
    Per-tenant costing configuration.
    Defines primary strategy, enabled strategies, accounts, and policies.
    """
    NEGATIVE_POLICY_CHOICES = [
        ("allow", "Allow"),
        ("block", "Block"),
        ("warn", "Warn"),
    ]

    primary_strategy = models.CharField(
        max_length=50,
        default="weighted_average",
        help_text="Strategy used for official reporting.",
    )
    enabled_strategies = models.JSONField(
        default=list,
        blank=True,
        help_text='List of strategy keys, e.g. ["weighted_average", "fifo", "lifo"].',
    )
    negative_inventory_policy = models.CharField(
        max_length=10,
        choices=NEGATIVE_POLICY_CHOICES,
        default="warn",
    )
    rounding_precision = models.SmallIntegerField(default=2)
    inventory_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default Inventory (balance sheet) account.",
    )
    cogs_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default COGS (income statement) account.",
    )
    adjustment_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Inventory Revaluation / Adjustment account.",
    )
    revenue_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default sales revenue account.",
    )
    purchase_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default purchase / goods receipt account.",
    )
    discount_given_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Default discount given on sales account.",
    )
    auto_post_primary = models.BooleanField(
        default=False,
        help_text="Auto-post accounting entries for primary strategy.",
    )
    auto_ingest_on_nfe_import = models.BooleanField(
        default=False,
        help_text="Automatically create stock movements when NF-e documents are imported.",
    )
    period_close_day = models.SmallIntegerField(
        default=0,
        help_text="0 = month-end.",
    )

    class Meta:
        verbose_name = "Tenant Costing Config"
        verbose_name_plural = "Tenant Costing Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                name="inventory_tenantcostingconfig_company_uniq",
            ),
        ]

    def __str__(self):
        return f"Costing config: {self.company}"


class InventoryValuationSnapshot(TenantAwareBaseModel):
    """
    Persisted valuation per strategy + product + warehouse + date.
    Enables side-by-side comparison without recomputation.
    """
    strategy = models.CharField(max_length=50, db_index=True)
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.CASCADE,
        related_name="valuation_snapshots",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="valuation_snapshots",
    )
    as_of_date = models.DateField(db_index=True)
    on_hand_qty = models.DecimalField(max_digits=15, decimal_places=4, default=0)
    on_hand_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    avg_unit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Inventory Valuation Snapshot"
        verbose_name_plural = "Inventory Valuation Snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "strategy", "product", "warehouse", "as_of_date"],
                name="inventory_valuationsnap_company_strat_prod_wh_date_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["strategy", "as_of_date"]),
        ]
        ordering = ["-as_of_date", "product"]

    def __str__(self):
        return f"{self.strategy} {self.product.code} @ {self.as_of_date}: {self.on_hand_value}"


class CogsAllocation(TenantAwareBaseModel):
    """
    COGS allocation per outbound movement per strategy.
    Records which layers were consumed and at what cost.
    """
    strategy = models.CharField(max_length=50, db_index=True)
    outbound_movement = models.ForeignKey(
        "inventory.StockMovement",
        on_delete=models.CASCADE,
        related_name="cogs_allocations",
    )
    product = models.ForeignKey(
        "billing.ProductService",
        on_delete=models.CASCADE,
        related_name="cogs_allocations",
    )
    qty = models.DecimalField(max_digits=15, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6)
    total_cogs = models.DecimalField(max_digits=18, decimal_places=2)
    layer_refs = models.JSONField(
        default=list,
        blank=True,
        help_text='[{"layer_id": 1, "qty_consumed": 5, "unit_cost": 10.00}, ...]',
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "COGS Allocation"
        verbose_name_plural = "COGS Allocations"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "strategy", "outbound_movement"],
                name="inventory_cogsallocation_company_strat_movement_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["strategy", "outbound_movement"]),
        ]

    def __str__(self):
        return f"{self.strategy} COGS {self.outbound_movement_id}: {self.total_cogs}"


class AccountingImpact(TenantAwareBaseModel):
    """
    Strategy-aware accounting posting record.
    Idempotency key prevents duplicate postings.
    """
    POSTING_TYPES = [
        ("cogs", "COGS"),
        ("period_close_adjustment", "Period Close Adjustment"),
        ("inventory_receipt", "Inventory Receipt"),
    ]
    SOURCE_TYPES = [
        ("stock_movement", "Stock Movement"),
        ("period_close", "Period Close"),
    ]

    strategy = models.CharField(max_length=50, db_index=True)
    posting_type = models.CharField(max_length=40, choices=POSTING_TYPES)
    source_document_type = models.CharField(max_length=40, choices=SOURCE_TYPES)
    source_document_id = models.PositiveIntegerField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    transaction = models.ForeignKey(
        "accounting.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_impacts",
    )
    accounts_detail = models.JSONField(
        default=list,
        help_text='[{"account_id": 1, "debit": 100, "credit": 0}, ...]',
    )
    total_debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Accounting Impact"
        verbose_name_plural = "Accounting Impacts"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "company",
                    "strategy",
                    "posting_type",
                    "source_document_type",
                    "source_document_id",
                ],
                name="inventory_accountingimpact_idempotency_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["strategy", "posting_type"]),
        ]

    def __str__(self):
        return f"{self.strategy} {self.posting_type} #{self.source_document_id}"
