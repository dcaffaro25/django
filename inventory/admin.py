# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import (
    Warehouse,
    UnitOfMeasure,
    UoMConversion,
    StockMovement,
    InventoryLayer,
    InventoryBalance,
    TenantCostingConfig,
    InventoryValuationSnapshot,
    CogsAllocation,
    AccountingImpact,
    InventoryAlert,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company", "is_active")
    list_filter = ("is_active", "company")


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "company")
    list_filter = ("company",)


@admin.register(UoMConversion)
class UoMConversionAdmin(admin.ModelAdmin):
    list_display = ("product", "from_uom", "to_uom", "factor", "company")
    list_filter = ("company",)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("id", "movement_type", "product", "quantity", "uom", "movement_date", "source_type", "reference")
    list_filter = ("movement_type", "source_type", "company")
    search_fields = ("reference", "idempotency_key")
    date_hierarchy = "movement_date"
    readonly_fields = ("idempotency_key", "metadata", "created_at")


@admin.register(InventoryLayer)
class InventoryLayerAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "remaining_qty", "unit_cost", "layer_date", "is_exhausted")
    list_filter = ("is_exhausted", "company")


@admin.register(InventoryBalance)
class InventoryBalanceAdmin(admin.ModelAdmin):
    list_display = ("product", "warehouse", "on_hand_qty", "last_movement_date")
    list_filter = ("company",)


@admin.register(TenantCostingConfig)
class TenantCostingConfigAdmin(admin.ModelAdmin):
    list_display = ("company", "primary_strategy", "negative_inventory_policy")


@admin.register(InventoryValuationSnapshot)
class InventoryValuationSnapshotAdmin(admin.ModelAdmin):
    list_display = ("strategy", "product", "warehouse", "as_of_date", "on_hand_qty", "on_hand_value")
    list_filter = ("strategy", "as_of_date")


@admin.register(CogsAllocation)
class CogsAllocationAdmin(admin.ModelAdmin):
    list_display = ("strategy", "outbound_movement", "product", "qty", "unit_cost", "total_cogs")
    list_filter = ("strategy",)


@admin.register(AccountingImpact)
class AccountingImpactAdmin(admin.ModelAdmin):
    list_display = ("strategy", "posting_type", "source_document_type", "source_document_id", "transaction")
    list_filter = ("strategy", "posting_type")


@admin.register(InventoryAlert)
class InventoryAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "severity", "title", "status", "product", "created_at")
    list_filter = ("alert_type", "severity", "status")
