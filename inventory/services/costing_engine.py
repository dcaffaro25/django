# -*- coding: utf-8 -*-
"""
Costing engine: orchestrates strategy computations, persists to ValuationSnapshot + CogsAllocation.
"""
from datetime import date
from decimal import Decimal

from django.db import transaction

from inventory.models import (
    StockMovement,
    InventoryValuationSnapshot,
    CogsAllocation,
)
from inventory.strategies import get_strategy, list_strategies
from inventory.strategies.base import LayerState


def _movements_to_layer_states(inbound_movements):
    """Convert inbound StockMovements to LayerState for strategies that need them."""
    from inventory.strategies.base import LayerState

    return [
        LayerState(
            layer_id=m.id,
            product_id=m.product_id,
            warehouse_id=m.warehouse_id,
            original_qty=m.quantity,
            remaining_qty=m.quantity,
            unit_cost=m.unit_cost or Decimal("0"),
            layer_date=m.movement_date,
            source_movement_id=m.id,
        )
        for m in inbound_movements
    ]


def compute_for_strategies(
    company,
    strategy_keys=None,
    start_date=None,
    end_date=None,
    product_ids=None,
    warehouse_ids=None,
):
    """
    Compute COGS allocations and ending inventory valuation for each strategy.
    Persists to InventoryValuationSnapshot and CogsAllocation.

    Args:
        company: Company instance
        strategy_keys: list of strategy keys, or None for all registered
        start_date: optional filter movements from
        end_date: as_of_date for valuation (default: today)
        product_ids: optional filter by products
        warehouse_ids: optional filter by warehouses

    Returns:
        dict: {
            "valuations": {strategy: [ValuationResult, ...]},
            "allocations": {strategy: [CogsResult, ...]},
            "errors": [...],
        }
    """
    if strategy_keys is None:
        strategy_keys = list_strategies()
    if end_date is None:
        end_date = date.today()

    qs = StockMovement.objects.filter(company=company)
    if start_date:
        qs = qs.filter(movement_date__date__gte=start_date)
    qs = qs.filter(movement_date__date__lte=end_date)
    if product_ids:
        qs = qs.filter(product_id__in=product_ids)
    if warehouse_ids:
        qs = qs.filter(warehouse_id__in=warehouse_ids)
    movements = list(qs.select_related("product", "warehouse").order_by("movement_date", "id"))

    context = {"company": company, "start_date": start_date, "end_date": end_date}
    results = {"valuations": {}, "allocations": {}, "errors": []}

    for key in strategy_keys:
        strategy = get_strategy(key)
        if not strategy:
            results["errors"].append(f"Unknown strategy: {key}")
            continue
        try:
            layers = strategy.rebuild_layers(movements, end_date, context)
            outbounds = [
                m
                for m in movements
                if m.movement_type in ("outbound", "return_out")
                or (
                    m.movement_type == "adjustment"
                    and (getattr(m, "metadata", None) or {}).get("direction") == "out"
                )
            ]
            allocations = strategy.allocate_cogs(outbounds, layers, end_date, context)
            valuations = strategy.value_ending_inventory(layers, end_date, context)

            results["valuations"][key] = valuations
            results["allocations"][key] = allocations

            with transaction.atomic():
                _persist_valuations(company, key, valuations, end_date)
                _persist_allocations(company, key, allocations)
        except Exception as e:
            results["errors"].append(f"{key}: {e}")

    return results


def _persist_valuations(company, strategy, valuations, as_of_date):
    """Upsert InventoryValuationSnapshot records."""
    from billing.models import ProductService
    from inventory.models import Warehouse

    for v in valuations:
        warehouse = None
        if v.warehouse_id:
            warehouse = Warehouse.objects.filter(company=company, id=v.warehouse_id).first()
        product = ProductService.objects.filter(company=company, id=v.product_id).first()
        if not product:
            continue
        InventoryValuationSnapshot.objects.update_or_create(
            company=company,
            strategy=strategy,
            product=product,
            warehouse=warehouse,
            as_of_date=as_of_date,
            defaults={
                "on_hand_qty": v.on_hand_qty,
                "on_hand_value": v.on_hand_value,
                "avg_unit_cost": v.avg_unit_cost,
            },
        )


def _persist_allocations(company, strategy, allocations):
    """Upsert CogsAllocation records."""
    from billing.models import ProductService

    for a in allocations:
        mov = StockMovement.objects.filter(company=company, id=a.outbound_movement_id).first()
        if not mov:
            continue
        product = ProductService.objects.filter(company=company, id=a.product_id).first()
        if not product:
            continue
        CogsAllocation.objects.update_or_create(
            company=company,
            strategy=strategy,
            outbound_movement=mov,
            defaults={
                "product": product,
                "qty": a.qty,
                "unit_cost": a.unit_cost,
                "total_cogs": a.total_cogs,
                "layer_refs": a.layer_refs,
            },
        )
