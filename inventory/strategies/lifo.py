# -*- coding: utf-8 -*-
"""
LIFO costing: consume newest layers first.
"""
from collections import defaultdict
from decimal import Decimal

from .base import BaseCostingStrategy, CogsResult, LayerState, ValuationResult


class LIFOStrategy(BaseCostingStrategy):
    key = "lifo"

    def allocate_cogs(self, outbound_movements, layers, as_of_date, context):
        """Consume layers in reverse chronological order (newest first). Process outbounds by date."""
        results = []
        sorted_outbounds = sorted(
            outbound_movements,
            key=lambda m: (m.movement_date, m.id),
        )
        layer_by_key = defaultdict(list)
        for L in layers:
            if L.remaining_qty <= 0:
                continue
            key = (L.product_id, L.warehouse_id or 0)
            layer_by_key[key].append(L)

        for key in layer_by_key:
            layer_by_key[key].sort(key=lambda x: (x.layer_date, x.layer_id or 0), reverse=True)

        for mov in sorted_outbounds:
            key = (mov.product_id, mov.warehouse_id or 0)
            available = layer_by_key.get(key, [])
            qty_left = mov.quantity
            total_cogs = Decimal("0")
            layer_refs = []
            consumed_per_layer = []

            for L in available:
                if qty_left <= 0:
                    break
                take = min(qty_left, L.remaining_qty)
                if take <= 0:
                    continue
                cost = take * L.unit_cost
                total_cogs += cost
                layer_refs.append({
                    "layer_id": L.layer_id,
                    "qty_consumed": float(take),
                    "unit_cost": float(L.unit_cost),
                })
                consumed_per_layer.append((L, take))
                qty_left -= take

            if mov.quantity > 0:
                unit_cost = (total_cogs / mov.quantity) if mov.quantity else Decimal("0")
                for L, take in consumed_per_layer:
                    L.remaining_qty -= take
                results.append(CogsResult(
                    outbound_movement_id=mov.id,
                    product_id=mov.product_id,
                    warehouse_id=mov.warehouse_id,
                    qty=mov.quantity,
                    unit_cost=unit_cost,
                    total_cogs=total_cogs,
                    layer_refs=layer_refs,
                ))
        return results

    def value_ending_inventory(self, layers, as_of_date, context):
        """Sum remaining qty * unit_cost per product/warehouse."""
        by_key = defaultdict(lambda: {"qty": Decimal("0"), "value": Decimal("0")})
        for L in layers:
            if L.remaining_qty <= 0:
                continue
            key = (L.product_id, L.warehouse_id)
            by_key[key]["qty"] += L.remaining_qty
            by_key[key]["value"] += L.remaining_qty * L.unit_cost

        out = []
        for (pid, wid), data in by_key.items():
            avg = data["value"] / data["qty"] if data["qty"] else None
            out.append(ValuationResult(
                product_id=pid,
                warehouse_id=wid if wid else None,
                on_hand_qty=data["qty"],
                on_hand_value=data["value"],
                avg_unit_cost=avg,
            ))
        return out

    def rebuild_layers(self, movements, as_of_date, context):
        """Build layers from inbound movements only. Consumption done by allocate_cogs."""
        from datetime import datetime
        layers = []
        for m in movements:
            if m.movement_type not in ("inbound", "return_in"):
                continue
            dt = m.movement_date
            if isinstance(dt, datetime) and as_of_date and dt.date() > as_of_date:
                continue
            layers.append(
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
            )
        return sorted(layers, key=lambda x: (x.layer_date, x.layer_id or 0), reverse=True)
