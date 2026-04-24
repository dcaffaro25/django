"""Inspect the Celery queue + worker state.

Prints a single-shot snapshot of what's in-flight (active tasks),
what's reserved but not yet started, what's scheduled for later,
the raw Redis queue depth(s), and a count of ImportSession rows
stuck in a non-terminal status. Meant to answer "is anything
stuck?" in one glance.

Usage::

    python manage.py celery_queue_stats
    python manage.py celery_queue_stats --json          # for tooling
    python manage.py celery_queue_stats --timeout 3     # inspect RPC timeout

Nothing this command does mutates state — it's read-only.

Does NOT require celery-beat/flower to be running. Talks directly
to Redis for queue depth and to the worker inspector for the live
task lists.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Show the current Celery queue + worker state."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit one JSON document instead of human output. "
                 "Useful for monitoring glue.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=3.0,
            help="Inspector RPC timeout in seconds (default: 3).",
        )
        parser.add_argument(
            "--queue",
            action="append",
            default=None,
            help="Redis queue name(s) to measure depth for. Defaults to 'celery' "
                 "(the default queue name). Pass multiple --queue flags for "
                 "additional queues.",
        )

    def handle(self, *args, **options):
        report = _collect_report(
            queues=options["queue"] or ["celery"],
            inspect_timeout=options["timeout"],
        )

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
            return

        _render_human(self.stdout, report)


def _collect_report(*, queues: List[str], inspect_timeout: float) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "queues": {},
        "workers": {},
        "totals": {
            "active": 0,
            "reserved": 0,
            "scheduled": 0,
        },
        "stale_import_sessions": {},
        "warnings": [],
    }

    # --- Redis queue depths ---------------------------------------------
    # Celery stores pending tasks as a Redis list. `LLEN <queue>` gives
    # the number of messages waiting. Active/reserved tasks are NOT
    # in this list — they've been claimed by a worker already.
    from nord_backend.celery import app as celery_app
    broker_url = celery_app.conf.broker_url
    try:
        import redis
        client = redis.Redis.from_url(
            broker_url, socket_connect_timeout=2, socket_timeout=2,
        )
        for q in queues:
            try:
                report["queues"][q] = client.llen(q)
            except Exception as exc:
                report["queues"][q] = f"error: {exc}"
                report["warnings"].append(f"LLEN {q}: {exc}")
    except Exception as exc:
        report["warnings"].append(f"redis client unavailable: {exc}")

    # --- Worker inspector (active / reserved / scheduled) ---------------
    # These RPC calls fan out through the broker. Wrap the whole block
    # so a dead/missing broker surfaces as a warning rather than a
    # stack trace — the rest of the report (Redis depth + stale
    # sessions) is still useful.
    active: Dict[str, Any] = {}
    reserved: Dict[str, Any] = {}
    scheduled: Dict[str, Any] = {}
    try:
        inspect = celery_app.control.inspect(timeout=inspect_timeout)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}
    except Exception as exc:
        report["warnings"].append(
            f"worker inspect failed (broker unreachable?): {exc}"
        )

    worker_names = set(active) | set(reserved) | set(scheduled)
    if not worker_names:
        report["warnings"].append(
            "no workers responded within timeout - either none are running "
            "or the broker connection is broken"
        )

    for name in sorted(worker_names):
        w_active = active.get(name, []) or []
        w_reserved = reserved.get(name, []) or []
        w_scheduled = scheduled.get(name, []) or []
        report["workers"][name] = {
            "active": [_task_brief(t) for t in w_active],
            "reserved": [_task_brief(t) for t in w_reserved],
            "scheduled": [_task_brief(t) for t in w_scheduled],
        }
        report["totals"]["active"] += len(w_active)
        report["totals"]["reserved"] += len(w_reserved)
        report["totals"]["scheduled"] += len(w_scheduled)

    # --- Stale ImportSession counts -------------------------------------
    # A v2 session stuck in analyzing/committing past the hard limit is
    # a stuckness signal even when the queue looks empty — the worker
    # died mid-task or the task was never picked up at all.
    try:
        from django.conf import settings as dj_settings
        from django.utils import timezone
        from datetime import timedelta
        from multitenancy.models import ImportSession

        hard_limit_s = int(
            getattr(dj_settings, "CELERY_TASK_TIME_LIMIT", 1800) or 1800
        )
        # Flag sessions older than the hard limit + 60s buffer; match the
        # reaper's own logic so the two views agree.
        cutoff = timezone.now() - timedelta(seconds=hard_limit_s + 60)

        stuck_qs = ImportSession.objects.filter(
            status__in=[
                ImportSession.STATUS_ANALYZING,
                ImportSession.STATUS_COMMITTING,
            ],
            updated_at__lt=cutoff,
        )
        report["stale_import_sessions"] = {
            "count": stuck_qs.count(),
            "oldest_pks": list(
                stuck_qs.order_by("updated_at")
                .values_list("pk", flat=True)[:10]
            ),
        }
    except Exception as exc:
        report["warnings"].append(f"stale-import-session check failed: {exc}")

    return report


def _task_brief(task: Dict[str, Any]) -> Dict[str, Any]:
    """Pull just the fields a human wants to see for a running task."""
    if not isinstance(task, dict):
        return {"raw": str(task)}
    return {
        "id": task.get("id"),
        "name": task.get("name"),
        "args": task.get("args"),
        "kwargs": task.get("kwargs"),
        "time_start": task.get("time_start"),
        "worker_pid": task.get("worker_pid"),
    }


def _render_human(stdout, report: Dict[str, Any]) -> None:
    def h(label: str) -> None:
        stdout.write(f"\n=== {label} ===")

    h("Redis queue depth")
    for q, depth in (report["queues"] or {"(none)": "-"}).items():
        stdout.write(f"  {q}: {depth}")

    h("Worker summary")
    totals = report["totals"]
    stdout.write(
        f"  {len(report['workers'])} worker(s) | "
        f"active={totals['active']} reserved={totals['reserved']} scheduled={totals['scheduled']}"
    )

    for name, lanes in (report["workers"] or {}).items():
        stdout.write(f"\n  * {name}")
        for lane in ("active", "reserved", "scheduled"):
            tasks = lanes.get(lane) or []
            if not tasks:
                continue
            stdout.write(f"      [{lane}] ({len(tasks)})")
            for t in tasks[:10]:
                stdout.write(
                    f"        - {t.get('name')} id={t.get('id')} pid={t.get('worker_pid')}"
                )
            if len(tasks) > 10:
                stdout.write(f"        … and {len(tasks) - 10} more")

    h("Stale v2 import sessions (non-terminal past hard limit)")
    stale = report.get("stale_import_sessions") or {}
    count = stale.get("count", 0)
    if count:
        stdout.write(f"  {count} stuck session(s); oldest pks: {stale.get('oldest_pks')}")
        stdout.write(
            "  -> Celery Beat should reap them every 5 min. If the count "
            "stays >0 between runs, verify the beat service is running."
        )
    else:
        stdout.write("  0 stuck")

    warnings = report.get("warnings") or []
    if warnings:
        h("Warnings")
        for w in warnings:
            stdout.write(f"  ! {w}")

    stdout.write("")  # final newline
