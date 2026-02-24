# -*- coding: utf-8 -*-
"""
Weighted Average costing: running average cost per product/warehouse.
"""
from collections import defaultdict
from decimal import Decimal

from .base import BaseCostingStrategy, CogsResult, LayerState, ValuationResult


class WeightedAverageStrategy(BaseCostingStrategy):
    key = "weighted_average"

    def allocate_cogs(self, outbound_movements, layers, as_of_date, context):
        """
        Layers for WAVG are synthetic: one per (product, warehouse) with remaining_qty and unit_cost.
        COGS = qty * avg_unit_cost; consuming reduces the synthetic layer qty.
        """
        results = []
        # Build avg state from layers (WAVG layers are one per product/warehouse)
        state_by_key = {}
        for L in layers:
            key = (L.product_id, L.warehouse_id or 0)
            if key not in state_by_key:
                state_by_key[key] = {"qty": Decimal("0"), "value": Decimal("0")}
            state_by_key[key]["qty"] += L.remaining_qty
            state_by_key[key]["value"] += L.remaining_qty * L.unit_cost

        sorted_outbounds = sorted(
            outbound_movements,
            key=lambda m: (m.movement_date, m.id),
        )

        layer_by_key = {(L.product_id, L.warehouse_id or 0): L for L in layers}

        for mov in sorted_outbounds:
            key = (mov.product_id, mov.warehouse_id or 0)
            state = state_by_key.get(key, {"qty": Decimal("0"), "value": Decimal("0")})
            qty = mov.quantity
            if state["qty"] <= 0:
                avg_cost = Decimal("0")
            else:
                avg_cost = state["value"] / state["qty"]

            total_cogs = qty * avg_cost
            take = min(qty, state["qty"])
            state["qty"] -= take
            state["value"] -= take * avg_cost

            # Mutate layer so value_ending_inventory sees correct state
            L = layer_by_key.get(key)
            if L:
                L.remaining_qty = state["qty"]
                L.unit_cost = (state["value"] / state["qty"]) if state["qty"] else Decimal("0")

            results.append(CogsResult(
                outbound_movement_id=mov.id,
                product_id=mov.product_id,
                warehouse_id=mov.warehouse_id,
                qty=mov.quantity,
                unit_cost=avg_cost,
                total_cogs=total_cogs,
                layer_refs=[{"strategy": "weighted_average", "unit_cost": float(avg_cost)}],
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
        """
        Build synthetic WAVG layers: one per (product, warehouse) with running qty and avg cost.
        Only process inbounds (and adjustment_in) - allocate_cogs will process outbounds.
        """
        from datetime import datetime
        by_key = defaultdict(lambda: {"qty": Decimal("0"), "value": Decimal("0")})
        sorted_movements = sorted(movements, key=lambda m: (m.movement_date, m.id))

        for m in sorted_movements:
            dt = m.movement_date
            if isinstance(dt, datetime) and as_of_date and dt.date() > as_of_date:
                continue
            key = (m.product_id, m.warehouse_id or 0)
            if m.movement_type in ("inbound", "return_in"):
                cost = (m.unit_cost or Decimal("0")) * m.quantity
                by_key[key]["qty"] += m.quantity
                by_key[key]["value"] += cost
            elif m.movement_type == "adjustment":
                meta = getattr(m, "metadata", None) or {}
                if meta.get("direction") == "in":
                    cost = (m.unit_cost or Decimal("0")) * m.quantity
                    by_key[key]["qty"] += m.quantity
                    by_key[key]["value"] += cost

        layers = []
        for (pid, wid), data in by_key.items():
            if data["qty"] <= 0:
                continue
            avg = data["value"] / data["qty"]
            layers.append(LayerState(
                layer_id=None,
                product_id=pid,
                warehouse_id=wid if wid else None,
                original_qty=data["qty"],
                remaining_qty=data["qty"],
                unit_cost=avg,
                layer_date=as_of_date,
                source_movement_id=None,
            ))
        return layers
