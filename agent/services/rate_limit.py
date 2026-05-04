"""Per-tool rate limiting backed by the audit table — Phase 0 expansion.

Reads ``settings.AGENT_TOOL_RATE_LIMITS`` (comma-separated
``name:N/window``) and parses it into a {tool_name: (count, window_s)}
map. Then :func:`check_rate_limit` counts recent ``AgentToolCallLog``
rows for the tenant + tool and returns whether the call should
proceed.

The audit table is the source of truth — no in-memory counters, no
Redis. A small index on ``(tool_name, status, -created_at)`` (already
in the model Meta) keeps the count query cheap.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from functools import lru_cache
from typing import Tuple

from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


_WINDOW_SECONDS = {"s": 1, "m": 60, "h": 3600}


@lru_cache(maxsize=1)
def _parsed_rules() -> dict[str, Tuple[int, int]]:
    """Parse ``settings.AGENT_TOOL_RATE_LIMITS`` once per process."""
    raw = getattr(settings, "AGENT_TOOL_RATE_LIMITS", "") or ""
    rules: dict[str, Tuple[int, int]] = {}
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, rate = chunk.split(":", 1)
        name = name.strip()
        try:
            count_str, _, window = rate.strip().partition("/")
            count = int(count_str)
            window_s = _WINDOW_SECONDS.get(window.strip().lower())
            if not window_s or count <= 0:
                continue
            rules[name] = (count, window_s)
        except (TypeError, ValueError):
            log.warning("agent.rate_limit.bad_rule rule=%r", chunk)
    return rules


def check_rate_limit(*, tool_name: str, company_id: int) -> dict | None:
    """Return ``None`` if the call may proceed, else an error blob.

    Counts ``AgentToolCallLog`` rows for the same ``(tool_name, company)``
    in the configured window. ``status`` is ignored — even rejected /
    errored calls count toward the budget so a misbehaving model can't
    drain the rate limit by always erroring.
    """
    rule = _parsed_rules().get(tool_name)
    if not rule:
        return None
    count, window_s = rule

    from agent.models import AgentToolCallLog
    cutoff = timezone.now() - timedelta(seconds=window_s)
    recent = AgentToolCallLog.objects.filter(
        tool_name=tool_name,
        company_id=company_id,
        created_at__gte=cutoff,
    ).count()
    if recent < count:
        return None
    return {
        "error": (
            f"Rate limit exceeded for tool {tool_name!r}: {recent} calls in "
            f"the last {window_s}s, cap is {count}. Wait or refine your "
            f"strategy."
        ),
        "rate_limited": True,
        "tool_name": tool_name,
        "limit": count,
        "window_seconds": window_s,
        "recent_calls": recent,
    }
