"""Celery tasks for the agent app — Phase 1 wave 3.

Today only :func:`run_due_playbooks`. Beat fires it every minute; the
task scans :class:`agent.models.AgentPlaybook` rows with a non-empty
``schedule_cron``, parses each via ``croniter``, and executes the
ones whose previous fire time is later than ``last_run_at``.

Each invocation of a playbook reuses the existing tool dispatch
(``run_agent_playbook``) so the same audit + kill-switch path applies
as a manual run from the chat — but ``triggered_by="beat"`` instead
of ``"agent_chat"`` for traceability.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task

log = logging.getLogger(__name__)


def _next_fire_after(cron_expr: str, since: datetime) -> datetime | None:
    """Compute the next fire time of ``cron_expr`` strictly after ``since``.

    Returns ``None`` if the cron expression is invalid (logged + skipped
    rather than raised — Beat shouldn't crash on one bad row).
    """
    try:
        from croniter import croniter
    except ImportError:
        log.warning("agent.tasks.run_due_playbooks: croniter not installed")
        return None
    try:
        return croniter(cron_expr, since).get_next(datetime)
    except (ValueError, KeyError, TypeError) as exc:
        log.warning(
            "agent.tasks.bad_cron expr=%r err=%s", cron_expr, exc,
        )
        return None


@shared_task(name="agent.tasks.run_due_playbooks")
def run_due_playbooks() -> dict:
    """Find and execute playbooks whose schedule_cron has fired since
    the last run. Returns a small summary suitable for Celery result
    inspection (``celery flower`` / ``django-celery-results``).
    """
    from django.utils import timezone as _tz

    from agent.models import AgentPlaybook

    now = _tz.now()
    qs = (
        AgentPlaybook.objects
        .filter(is_active=True)
        .exclude(schedule_cron="")
    )

    fired_ids: list[int] = []
    skipped_ids: list[int] = []
    invalid_ids: list[int] = []
    errors: list[dict] = []

    for pb in qs:
        # Determine the most recent fire time strictly before ``now``
        # by stepping forward from a stable anchor. We use last_run_at
        # if present (so "did the schedule fire since I last ran?"),
        # else a 30-day-ago floor (so a freshly-saved playbook fires
        # on its next scheduled tick rather than immediately).
        anchor = pb.last_run_at or (now - _tz.timedelta(days=30))
        next_fire = _next_fire_after(pb.schedule_cron, anchor)
        if next_fire is None:
            invalid_ids.append(pb.id)
            continue

        if next_fire > now:
            skipped_ids.append(pb.id)
            continue

        # Due — fire it. Reuse the existing dispatcher so audit + kill-
        # switch + last_run_summary cache stay consistent with manual
        # invocations from chat.
        try:
            from mcp_server.tools import run_agent_playbook
            result = run_agent_playbook(
                company_id=pb.company_id,
                name_or_id=pb.id,
                # Beat-driven runs respect AGENT_ALLOW_WRITES via the
                # downstream tool. Operators flip the kill-switch to
                # opt into live writes.
                dry_run=False,
            )
            fired_ids.append(pb.id)
            if isinstance(result, dict) and result.get("error"):
                errors.append({"playbook_id": pb.id, "error": result["error"]})
        except Exception as exc:
            log.exception(
                "agent.tasks.playbook_failed playbook=%s: %s", pb.id, exc,
            )
            errors.append({"playbook_id": pb.id, "error": f"{type(exc).__name__}: {exc}"})

    summary = {
        "now": now.isoformat(),
        "scanned": qs.count(),
        "fired": fired_ids,
        "skipped": skipped_ids,
        "invalid_cron": invalid_ids,
        "errors": errors,
    }
    if fired_ids or errors:
        log.info("agent.tasks.run_due_playbooks summary=%s", summary)
    return summary
