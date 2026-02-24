# -*- coding: utf-8 -*-
"""
Inventory serializers.
"""
from rest_framework import serializers

from .models import (
    Warehouse,
    UnitOfMeasure,
    UoMConversion,
    StockMovement,
    InventoryLayer,
    InventoryBalance,
    InventoryAlert,
)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "code",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = [
            "id",
            "code",
            "name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UoMConversionSerializer(serializers.ModelSerializer):
    from_uom_code = serializers.CharField(source="from_uom.code", read_only=True)
    to_uom_code = serializers.CharField(source="to_uom.code", read_only=True)

    class Meta:
        model = UoMConversion
        fields = [
            "id",
            "product",
            "from_uom",
            "to_uom",
            "from_uom_code",
            "to_uom_code",
            "factor",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class StockMovementSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    uom_code = serializers.CharField(source="uom.code", read_only=True)
    warehouse_code = serializers.CharField(
        source="warehouse.code", read_only=True, allow_null=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "movement_type",
            "product",
            "product_code",
            "product_name",
            "warehouse",
            "warehouse_code",
            "quantity",
            "unit_cost",
            "uom",
            "uom_code",
            "movement_date",
            "source_type",
            "reference",
            "idempotency_key",
            "nfe_item",
            "nota_fiscal",
            "metadata",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class InventoryAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryAlert
        fields = [
            "id",
            "alert_type",
            "severity",
            "product",
            "nfe_item",
            "nota_fiscal",
            "title",
            "description",
            "evidence",
            "status",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class InventoryBalanceSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    warehouse_code = serializers.CharField(
        source="warehouse.code", read_only=True, allow_null=True
    )

    class Meta:
        model = InventoryBalance
        fields = [
            "id",
            "product",
            "product_code",
            "product_name",
            "warehouse",
            "warehouse_code",
            "on_hand_qty",
            "last_movement_date",
            "last_rebuilt_at",
        ]
