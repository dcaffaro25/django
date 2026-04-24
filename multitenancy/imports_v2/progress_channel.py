"""Redis-backed live progress channel for v2 imports (Phase 6.z-g).

The DB's ``ImportSession.progress`` JSONField is the canonical record
but can't carry intra-commit row-level updates: the whole commit runs
inside ``transaction.atomic()``, so any session.save from the worker
is invisible to the polling frontend until the block commits.

This module publishes high-frequency progress to Redis (which is
already in the stack as the Celery broker) outside the DB
transaction. The polling endpoint reads Redis first for non-terminal
sessions, falling back to the DB snapshot if the key is missing or
Redis is unavailable — so the system degrades cleanly to the
stage-level progress that shipped in 6.z-e.

Key lifecycle:

  * Key:   ``imports_v2:progress:<session_pk>``
  * Value: ``json.dumps(progress_dict)``
  * TTL:   ``CELERY_TASK_TIME_LIMIT + 120`` seconds — covers the
           worst-case worker run plus a small grace. The key
           expires on its own; explicit delete happens when the
           worker flips the session to a terminal status.

REDIS_URL absent (tests, dev without a broker): the channel becomes
a no-op. Callers don't need to special-case this — they just lose
the Redis-backed updates and rely on the DB snapshot.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "imports_v2:progress:"


def _redis_client():  # -> redis.Redis | None
    """Return a Redis client configured from ``REDIS_URL``, or None.

    Connection is cheap and pooled by the redis-py client itself.
    Returns None in any failure path (missing URL, import error,
    connection refused) — callers treat None as "channel disabled".
    """
    url = getattr(settings, "CELERY_BROKER_URL", None) or getattr(
        settings, "REDIS_URL", None,
    )
    if not url or not url.startswith(("redis://", "rediss://")):
        return None
    try:
        import redis  # imported lazily so the module import never crashes
        return redis.Redis.from_url(
            url,
            socket_connect_timeout=1,
            socket_timeout=1,
            # No retry — progress is best-effort; a slow Redis shouldn't
            # drag the worker loop.
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("failed to build redis client for progress channel", exc_info=True)
        return None


def _ttl_seconds() -> int:
    hard_limit = int(
        getattr(settings, "CELERY_TASK_TIME_LIMIT", 1800) or 1800
    )
    # +120s grace so a task grazing the limit still has its progress
    # visible for a beat after it finishes.
    return hard_limit + 120


def publish(session_pk: int, fields: Dict[str, Any]) -> None:
    """Merge-write ``fields`` into the Redis progress key for a session.

    Reads the existing blob (if any), merges the new fields into it,
    writes back. Not atomic across the read+write pair but it doesn't
    need to be — the only writer is the worker processing this
    particular session, so there's no contention.

    Errors are swallowed: progress writes must not block the import.
    """
    client = _redis_client()
    if client is None:
        return
    key = f"{_KEY_PREFIX}{session_pk}"
    try:
        existing_raw = client.get(key)
        existing: Dict[str, Any] = {}
        if existing_raw:
            try:
                parsed = json.loads(existing_raw)
                if isinstance(parsed, dict):
                    existing = parsed
            except (ValueError, TypeError):
                existing = {}
        merged = {**existing, **fields}
        # Stamp updated_at automatically so the frontend can show
        # "atualizado há Ns" without a separate field.
        from django.utils import timezone
        merged["updated_at"] = timezone.now().isoformat()
        client.set(key, json.dumps(merged), ex=_ttl_seconds())
    except Exception:  # pragma: no cover
        logger.debug("progress publish failed for session %s", session_pk, exc_info=True)


def read(session_pk: int) -> Optional[Dict[str, Any]]:
    """Return the current Redis snapshot for a session, or None.

    Serializer merges this with ``session.progress`` — Redis wins for
    non-terminal sessions (freshest), DB wins after the worker
    finishes and clears the key.
    """
    client = _redis_client()
    if client is None:
        return None
    key = f"{_KEY_PREFIX}{session_pk}"
    try:
        raw = client.get(key)
        if not raw:
            return None
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # pragma: no cover
        logger.debug("progress read failed for session %s", session_pk, exc_info=True)
    return None


def clear(session_pk: int) -> None:
    """Delete the Redis key — called by the worker on terminal status.

    Cleanup after a successful commit or explicit error. The TTL
    would clean it up eventually either way; clearing early keeps
    the key space tidy.
    """
    client = _redis_client()
    if client is None:
        return
    key = f"{_KEY_PREFIX}{session_pk}"
    try:
        client.delete(key)
    except Exception:  # pragma: no cover
        logger.debug("progress clear failed for session %s", session_pk, exc_info=True)
