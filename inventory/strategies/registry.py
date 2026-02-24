# -*- coding: utf-8 -*-
"""
Strategy registry for pluggable costing engines.
"""
from typing import Dict, List, Optional

_strategies: Dict[str, "BaseCostingStrategy"] = {}


def register_strategy(strategy: "BaseCostingStrategy") -> None:
    _strategies[strategy.key] = strategy


def get_strategy(key: str) -> Optional["BaseCostingStrategy"]:
    return _strategies.get(key)


def list_strategies() -> List[str]:
    return list(_strategies.keys())
