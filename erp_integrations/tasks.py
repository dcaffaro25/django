"""
Celery tasks for ERP sync jobs.
"""

import logging
from datetime import datetime, timezone as dt_tz

from celery import shared_task
from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, soft_time_limit=600, time_limit=660)
def run_erp_sync_task(self, job_id: int, dry_run: bool = False):
    """Execute a single ERPSyncJob. Called manually or by Beat."""
    from .services.omie_sync_service import execute_sync

    return execute_sync(job_id, dry_run=dry_run)


def _is_job_due(schedule_rrule: str, last_synced_at, now: datetime) -> bool:
    """
    Check whether a job is due for execution based on its iCal RRULE
    and last successful sync time.

    The logic: parse the RRULE starting from last_synced_at (or epoch if never
    synced). If the next scheduled occurrence is at or before *now*, the job
    is due.
    """
    try:
        dtstart = last_synced_at or datetime(2020, 1, 1, tzinfo=dt_tz.utc)
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=dt_tz.utc)

        rule = rrulestr(schedule_rrule, dtstart=dtstart, ignoretz=True)
        next_occurrence = rule.after(dtstart, inc=False)
        if next_occurrence is None:
            return False
        if next_occurrence.tzinfo is None:
            next_occurrence = next_occurrence.replace(tzinfo=dt_tz.utc)
        return next_occurrence <= now
    except Exception:
        logger.warning(
            "Could not parse schedule_rrule %r, skipping.", schedule_rrule
        )
        return False


@shared_task
def run_all_due_syncs():
    """
    Celery Beat entry (every 15 min): find active ERPSyncJobs whose
    schedule_rrule indicates they are due, skip jobs already running,
    and dispatch run_erp_sync_task for each.
    """
    from .models import ERPSyncJob

    now = datetime.now(dt_tz.utc)

    candidates = list(
        ERPSyncJob.objects.filter(is_active=True, schedule_rrule__isnull=False)
        .exclude(schedule_rrule="")
        .exclude(last_sync_status="running")
        .only(
            "id", "schedule_rrule", "last_synced_at", "last_sync_status"
        )
    )

    dispatched = []
    skipped = []
    for job in candidates:
        if _is_job_due(job.schedule_rrule, job.last_synced_at, now):
            run_erp_sync_task.delay(job.id)
            dispatched.append(job.id)
        else:
            skipped.append(job.id)

    logger.info(
        "run_all_due_syncs: dispatched=%d skipped=%d",
        len(dispatched), len(skipped),
    )
    return {"dispatched": dispatched, "skipped": skipped}
