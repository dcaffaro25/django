# -*- coding: utf-8 -*-
from .base import BaseCostingStrategy, CogsResult, ValuationResult, LayerState
from .registry import get_strategy, list_strategies, register_strategy
from .weighted_average import WeightedAverageStrategy
from .fifo import FIFOStrategy
from .lifo import LIFOStrategy

# Auto-register built-in strategies
register_strategy(WeightedAverageStrategy())
register_strategy(FIFOStrategy())
register_strategy(LIFOStrategy())

__all__ = [
    "BaseCostingStrategy",
    "CogsResult",
    "ValuationResult",
    "LayerState",
    "get_strategy",
    "list_strategies",
    "register_strategy",
    "WeightedAverageStrategy",
    "FIFOStrategy",
    "LIFOStrategy",
]
