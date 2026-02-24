# -*- coding: utf-8 -*-
"""
Base costing strategy interface. All strategies implement allocate_cogs, value_ending_inventory, rebuild_layers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class LayerState:
    """Represents an inventory layer (or virtual layer for WAVG)."""
    layer_id: Optional[int]  # None for WAVG synthetic
    product_id: int
    warehouse_id: Optional[int]
    original_qty: Decimal
    remaining_qty: Decimal
    unit_cost: Decimal
    layer_date: Any  # datetime
    source_movement_id: Optional[int]


@dataclass
class CogsResult:
    """Result of COGS allocation for a single outbound movement."""
    outbound_movement_id: int
    product_id: int
    warehouse_id: Optional[int]
    qty: Decimal
    unit_cost: Decimal
    total_cogs: Decimal
    layer_refs: List[dict]  # [{"layer_id": 1, "qty_consumed": 5, "unit_cost": 10}]


@dataclass
class ValuationResult:
    """Ending inventory valuation for a product/warehouse."""
    product_id: int
    warehouse_id: Optional[int]
    on_hand_qty: Decimal
    on_hand_value: Decimal
    avg_unit_cost: Optional[Decimal]


class BaseCostingStrategy(ABC):
    """Abstract base for costing strategies."""

    key: str = "base"

    @abstractmethod
    def allocate_cogs(
        self,
        outbound_movements: list,
        layers: List[LayerState],
        as_of_date: Any,
        context: Dict[str, Any],
    ) -> List[CogsResult]:
        """
        Allocate cost from layers to outbound movements.
        Returns allocation records per movement.
        """

    @abstractmethod
    def value_ending_inventory(
        self,
        layers: List[LayerState],
        as_of_date: Any,
        context: Dict[str, Any],
    ) -> List[ValuationResult]:
        """Value remaining inventory layers as of date."""

    @abstractmethod
    def rebuild_layers(
        self,
        movements: list,
        as_of_date: Any,
        context: Dict[str, Any],
    ) -> List[LayerState]:
        """Rebuild layer state from movement history (full recomputation)."""
