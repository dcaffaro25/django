# -*- coding: utf-8 -*-
"""
Valuation service: comparison reports, side-by-side strategy deltas.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from inventory.models import InventoryValuationSnapshot, CogsAllocation


def get_comparison_report(company, start_date, end_date, strategies=None):
    """
    Side-by-side comparison: COGS, ending inventory, gross profit by strategy.
    Returns aggregated totals and deltas vs first strategy.
    """
    if strategies is None:
        strategies = ["weighted_average", "fifo", "lifo"]

    snapshots = InventoryValuationSnapshot.objects.filter(
        company=company,
        strategy__in=strategies,
        as_of_date=end_date,
    )
    allocations = CogsAllocation.objects.filter(
        company=company,
        strategy__in=strategies,
        outbound_movement__movement_date__date__gte=start_date,
        outbound_movement__movement_date__date__lte=end_date,
    )

    by_strategy = {}
    for s in strategies:
        by_strategy[s] = {
            "total_cogs": Decimal("0"),
            "ending_inventory_value": Decimal("0"),
            "gross_profit": None,
        }

    for row in allocations.values("strategy").annotate(total=Sum("total_cogs")):
        by_strategy[row["strategy"]]["total_cogs"] = row["total"] or Decimal("0")

    for row in snapshots.values("strategy").annotate(total=Sum("on_hand_value")):
        by_strategy[row["strategy"]]["ending_inventory_value"] = row["total"] or Decimal("0")

    baseline = strategies[0] if strategies else None
    deltas = {}
    for s in strategies:
        deltas[s] = {}
        if baseline and s != baseline:
            deltas[s]["cogs_vs_baseline"] = float(
                by_strategy[s]["total_cogs"] - by_strategy[baseline]["total_cogs"]
            )
            deltas[s]["inventory_vs_baseline"] = float(
                by_strategy[s]["ending_inventory_value"]
                - by_strategy[baseline]["ending_inventory_value"]
            )

    out_strategies = {}
    for s, data in by_strategy.items():
        out_strategies[s] = {
            "total_cogs": float(data["total_cogs"]),
            "ending_inventory_value": float(data["ending_inventory_value"]),
            "gross_profit": data["gross_profit"],
        }

    return {
        "strategies": out_strategies,
        "deltas": deltas,
        "baseline": baseline,
        "date_range": {"start": str(start_date), "end": str(end_date)},
    }


def get_sku_drilldown(company, product_id, start_date, end_date, strategies=None):
    """Per-SKU delta across strategies."""
    if strategies is None:
        strategies = ["weighted_average", "fifo", "lifo"]

    snapshots = InventoryValuationSnapshot.objects.filter(
        company=company,
        product_id=product_id,
        strategy__in=strategies,
        as_of_date=end_date,
    )
    allocations = CogsAllocation.objects.filter(
        company=company,
        product_id=product_id,
        strategy__in=strategies,
        outbound_movement__movement_date__date__gte=start_date,
        outbound_movement__movement_date__date__lte=end_date,
    )

    by_strategy = {s: {"cogs": Decimal("0"), "ending_value": Decimal("0")} for s in strategies}
    for a in allocations:
        by_strategy[a.strategy]["cogs"] += a.total_cogs
    for s in snapshots:
        by_strategy[s.strategy]["ending_value"] += s.on_hand_value

    out = {s: {"cogs": float(by_strategy[s]["cogs"]), "ending_value": float(by_strategy[s]["ending_value"])} for s in strategies}
    return {"product_id": product_id, "by_strategy": out}


def get_movement_drilldown(company, movement_id, strategies=None):
    """Per outbound movement: how allocated layers differ across strategies."""
    if strategies is None:
        strategies = ["weighted_average", "fifo", "lifo"]

    allocations = CogsAllocation.objects.filter(
        company=company,
        outbound_movement_id=movement_id,
        strategy__in=strategies,
    )
    return {
        "movement_id": movement_id,
        "allocations": [
            {
                "strategy": a.strategy,
                "qty": float(a.qty),
                "unit_cost": float(a.unit_cost),
                "total_cogs": float(a.total_cogs),
                "layer_refs": a.layer_refs,
            }
            for a in allocations
        ],
    }
