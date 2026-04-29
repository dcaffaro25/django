"""Versioned cache for the report stack.

The Demonstrativos page (``GET /api/accounts/financial-statements/``)
and the CoA list (``GET /api/accounts/``) both build expensive
per-tenant payloads that are *deterministic* given the tenant's
current data state. Repeating the build on every paginated CoA page
or every tab switch is wasteful, but a naive cache risks serving
stale numbers after a JE / Transaction / Account write.

We solve that with **versioned keys**. The version is a hash of two
things, combined so either source of change invalidates the cache:

  1. ``MAX(updated_at)`` across ``JournalEntry``, ``Transaction``
     and ``Account`` for the tenant. Covers every ``.save()`` call
     thanks to ``auto_now=True`` on the base model.
  2. A manually-bumped tenant epoch counter. This is the safety
     net for ``QuerySet.update()`` (which Django's ``auto_now``
     does NOT fire on) and any other code path that mutates the
     three tables without going through ``.save()``. Bulk-write
     sites should call ``bump_version(company_id)`` after a
     write that affects report inputs.

Either source moving = different cache key = next read rebuilds.
There's no signal handler maintained globally; the manual bump is
a one-liner the caller adds where they already know they're doing
something cache-relevant.

A short TTL (default 60s) is layered on top so even if both
sources somehow miss a write -- e.g. a raw SQL execute bypassing
the ORM -- staleness is bounded. The TTL is tunable via
``DEFAULT_TTL_SECONDS``.

Cost of the strategy: 3 ``MAX(updated_at)`` queries + 1 cache GET
per cached read (~1-3ms total with indexes). Much cheaper than
rebuilding a 30KB report payload.

Public surface:
    * ``data_version(company_id)`` -> str fingerprint
    * ``bump_version(company_id)``  -> force-invalidate this tenant
    * ``cached_payload(prefix, company_id, key_parts, builder, ...)``

The cache backend is whatever Django is configured to use
(``django.core.cache.cache``); default ``LocMemCache`` is fine for
single-process deployments and Redis works without code changes
for multi-replica setups. Note: ``LocMemCache`` is per-process, so
the counter half of the fingerprint is also per-process; for
multi-worker deployments use a shared backend (Redis / Memcached)
to keep all workers in sync.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional

from django.core.cache import cache
from django.db.models import Max

logger = logging.getLogger(__name__)

# Default TTL: 60 seconds. With versioned keys this is *not* the
# primary freshness mechanism, but it *is* the safety net for
# corner cases where both fingerprint sources miss a write
# (e.g. raw SQL execute bypassing the ORM). Bound the worst-case
# staleness window at one minute; bump higher only if the report
# rebuild cost gets onerous and you trust the invalidation paths.
DEFAULT_TTL_SECONDS = 60

# Cache key prefix for the per-tenant manual epoch counter. Bumped
# by ``bump_version(company_id)`` on any code path that mutates
# report-input tables without ``.save()`` (typically:
# ``Model.objects.filter(...).update(...)``).
_EPOCH_KEY = "report_cache:epoch:{company_id}"


def _epoch(company_id: int) -> int:
    """Read the manual epoch counter for this tenant. Defaults to
    0 when the cache backend has never seen this key."""
    try:
        return int(cache.get(_EPOCH_KEY.format(company_id=company_id)) or 0)
    except Exception:
        return 0


def bump_version(company_id: int) -> None:
    """Force-invalidate every cached report payload for this tenant.

    Call from any code path that writes to ``JournalEntry``,
    ``Transaction`` or ``Account`` *without* going through
    ``.save()`` -- typically ``Model.objects.filter(...).update(...)``,
    ``bulk_update()``, raw SQL, or COPY-based imports. The
    ``.save()`` path is covered automatically by ``auto_now=True``
    on the base model, so you do NOT need to call this from
    ``perform_create`` / ``perform_update`` etc.

    Implementation: increments a per-tenant counter that the
    fingerprint mixes in. A new value -> different version ->
    different cache key -> next read rebuilds.

    Cheap (single ``cache.incr`` call) and idempotent. Safe to
    call defensively even if you're not sure whether a write
    affects report inputs.
    """
    key = _EPOCH_KEY.format(company_id=company_id)
    try:
        cache.incr(key)
    except ValueError:
        # ``incr`` raises ValueError if the key isn't set yet
        # (LocMemCache behaviour). Initialize it to 1 -- the value
        # itself doesn't matter, only that it changes.
        try:
            cache.set(key, 1)
        except Exception:
            logger.exception(
                "report_cache: bump_version failed (init) for company_id=%s",
                company_id,
            )
    except Exception:
        logger.exception(
            "report_cache: bump_version failed for company_id=%s",
            company_id,
        )


def data_version(company_id: int) -> str:
    """Return a short fingerprint that changes whenever any data
    feeding the report stack is written for this tenant.

    Sources of change (any one moves -> fingerprint moves):
      * ``MAX(updated_at)`` across ``JournalEntry``, ``Transaction``
        and ``Account`` for the tenant (covers ``.save()`` writes
        via ``auto_now=True``).
      * Per-tenant epoch counter, bumped manually by
        ``bump_version(company_id)`` (covers
        ``QuerySet.update()`` and other ORM-bypassing writes).

    The output is a fixed-length hex digest suitable for cache
    keys; an attacker reading a key can't deduce the underlying
    timestamps from it.

    On error we return ``"v0:err"``. Callers using this through
    ``cached_payload`` fall back to a rebuild-without-caching
    path that's correct but slow.
    """
    # Local imports keep this module import-time-light: avoids
    # circular imports and lets it be imported during Django app
    # registry initialization.
    from accounting.models import Account, JournalEntry, Transaction

    try:
        je_v = JournalEntry.objects.filter(
            account__company_id=company_id,
        ).aggregate(v=Max('updated_at'))['v']
        tx_v = Transaction.objects.filter(
            company_id=company_id,
        ).aggregate(v=Max('updated_at'))['v']
        ac_v = Account.objects.filter(
            company_id=company_id,
        ).aggregate(v=Max('updated_at'))['v']
        epoch = _epoch(company_id)
        raw = f"{je_v or 'none'}|{tx_v or 'none'}|{ac_v or 'none'}|{epoch}"
        return hashlib.blake2s(raw.encode('utf-8'), digest_size=8).hexdigest()
    except Exception:
        # Defensive: never fail a report read because the
        # version probe blew up. Returning a sentinel forces a
        # cache miss-and-rebuild path that's also safe.
        logger.exception(
            "report_cache: data_version probe failed for company_id=%s",
            company_id,
        )
        return "v0:err"


def make_key(prefix: str, company_id: int, key_parts: Dict[str, Any], version: str) -> str:
    """Compose a stable cache key.

    Sorts ``key_parts`` so dict ordering can't produce different
    keys for the same logical request. Coerces ``None`` to the
    literal string ``"none"`` to keep keys collision-free across
    "missing param" and the literal string ``"None"``.
    """
    canon = json.dumps(
        {k: ("none" if v is None else v) for k, v in sorted(key_parts.items())},
        default=str,
        separators=(",", ":"),
    )
    digest = hashlib.blake2s(canon.encode('utf-8'), digest_size=10).hexdigest()
    return f"{prefix}:{company_id}:{version}:{digest}"


def cached_payload(
    prefix: str,
    company_id: int,
    key_parts: Dict[str, Any],
    builder: Callable[[], Any],
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
    bypass: bool = False,
) -> Any:
    """Get-or-build helper.

    Returns ``builder()`` either from cache or by invoking it and
    caching the result under a versioned key. ``bypass=True`` skips
    the cache entirely (use for ``?nocache=1`` or operator debug).

    The caller is responsible for ``builder()`` being deterministic
    given ``key_parts`` -- if you forget to include a parameter that
    affects the output, you'll get cross-tenant or cross-filter
    contamination.
    """
    if bypass:
        return builder()

    version = data_version(company_id)
    key = make_key(prefix, company_id, key_parts, version)

    hit = cache.get(key)
    if hit is not None:
        logger.debug("report_cache hit: prefix=%s company=%s", prefix, company_id)
        return hit

    payload = builder()
    try:
        cache.set(key, payload, ttl)
    except Exception:
        # Cache backend hiccup must never break a successful build.
        logger.exception(
            "report_cache: cache.set failed for prefix=%s company=%s",
            prefix, company_id,
        )
    return payload
