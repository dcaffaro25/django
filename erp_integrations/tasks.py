"""
Celery tasks for ERP sync jobs.
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, soft_time_limit=600, time_limit=660)
def run_erp_sync_task(self, job_id: int, dry_run: bool = False):
    """Execute a single ERPSyncJob. Called manually or by Beat."""
    from .services.omie_sync_service import execute_sync

    return execute_sync(job_id, dry_run=dry_run)


@shared_task
def run_all_due_syncs():
    """
    Celery Beat entry: find all active ERPSyncJobs with schedule_rrule,
    dispatch run_erp_sync_task for each.
    """
    from .models import ERPSyncJob

    jobs = list(
        ERPSyncJob.objects.filter(is_active=True, schedule_rrule__isnull=False)
        .exclude(schedule_rrule="")
        .values_list("id", flat=True)
    )
    for job_id in jobs:
        run_erp_sync_task.delay(job_id)
    return {"dispatched": len(jobs)}
