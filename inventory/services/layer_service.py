# -*- coding: utf-8 -*-
"""
Layer service: create InventoryLayer from inbound movements, consume for costing.
"""
from decimal import Decimal

from django.db import transaction

from inventory.models import StockMovement, InventoryLayer


def create_layer_from_inbound(movement):
    """
    Create an InventoryLayer from an inbound StockMovement.
    Called when we persist layers (optional; strategies can work with in-memory state).
    """
    if movement.movement_type not in ("inbound", "return_in"):
        return None
    layer, _ = InventoryLayer.objects.get_or_create(
        company=movement.company,
        source_movement=movement,
        defaults={
            "product": movement.product,
            "warehouse": movement.warehouse,
            "original_qty": movement.quantity,
            "remaining_qty": movement.quantity,
            "unit_cost": movement.unit_cost or Decimal("0"),
            "layer_date": movement.movement_date,
        },
    )
    return layer
