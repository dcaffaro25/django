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


@shared_task(bind=True, max_retries=1, soft_time_limit=1200, time_limit=1320)
def run_erp_pipeline_task(self, pipeline_id: int, dry_run: bool = False):
    """Execute a composite ERPSyncPipeline. Longer limits than single-job sync."""
    from .services.pipeline_service import execute_pipeline

    return execute_pipeline(pipeline_id, dry_run=dry_run)


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


@shared_task(bind=True, max_retries=1, soft_time_limit=1500, time_limit=1620)
def refresh_omie_pipeline_incremental(self, pipeline_id: int, lookback_days: int = 30):
    """Run a Listar*-based pipeline with a rolling date-modified window.

    Looks up the pipeline's most recent ``completed`` run and pulls only
    records modified since (run.started_at - 1 day) to catch any
    upstream-Omie updates that happened mid-run. On a fresh pipeline
    (no prior completed run), backfills ``lookback_days`` of history.

    Per-step param overrides are wired in via
    :func:`execute_pipeline(... param_overrides_by_step=...)`. The
    overrides translate ``since`` / ``until`` into Omie's per-call
    field naming (``filtrar_por_alteracao_de`` for the most-modern
    Listar* family, ``dDtIncDe`` for ListarMovimentos).

    The pipeline's existing ``unique_id_config`` upserts re-fetched
    records — ``record_hash`` mismatches turn into ``updated`` rows,
    matches into ``skipped`` rows. Net result: ERPRawRecord stays
    bounded at the count of distinct external_ids in Omie.
    """
    from datetime import date, timedelta

    from django.utils import timezone as dj_tz

    from .models import ERPSyncPipeline, ERPSyncPipelineRun
    from .services.pipeline_service import execute_pipeline

    pipeline = ERPSyncPipeline.objects.filter(pk=pipeline_id, is_active=True).first()
    if pipeline is None:
        return {"success": False, "error": f"pipeline {pipeline_id} not found / inactive"}

    last_completed = (
        ERPSyncPipelineRun.objects
        .filter(pipeline=pipeline, status="completed")
        .order_by("-started_at").first()
    )
    if last_completed and last_completed.started_at:
        # Buffer back one day to catch races between Omie's "modified at"
        # timestamps and our run boundary.
        since_dt = last_completed.started_at - timedelta(days=1)
    else:
        since_dt = dj_tz.now() - timedelta(days=lookback_days)

    until_dt = dj_tz.now() + timedelta(days=1)

    since_br = since_dt.strftime("%d/%m/%Y")
    until_br = until_dt.strftime("%d/%m/%Y")

    # Build per-step overrides keyed by step.order. Knowledge of which
    # field-names each call accepts lives here — keep this in sync with
    # the Omie service-list when adding new pipelines.
    step_overrides: dict[int, dict] = {}
    for step in pipeline.steps.all().select_related("api_definition"):
        call = step.api_definition.call
        if call == "ListarPedidos":
            step_overrides[step.order] = {
                "filtrar_por_alteracao_de": since_br,
                "filtrar_por_alteracao_ate": until_br,
            }
        elif call == "ListarClientes":
            step_overrides[step.order] = {
                "filtrar_por_alteracao_de": since_br,
                "filtrar_por_alteracao_ate": until_br,
            }
        elif call == "ListarProdutos":
            step_overrides[step.order] = {
                "filtrar_apenas_alteracao": "S",
                "filtrar_por_alteracao_de": since_br,
                "filtrar_por_alteracao_ate": until_br,
            }
        elif call == "ListarMovimentos":
            # Movimentos uses different naming + CamelCase pagination.
            step_overrides[step.order] = {
                "dDtIncDe": since_br,
                "dDtIncAte": until_br,
            }
        elif call == "ListarContasReceber":
            step_overrides[step.order] = {
                "filtrar_apenas_alteracao": "S",
                "filtrar_por_alteracao_de": since_br,
                "filtrar_por_alteracao_ate": until_br,
            }
        elif call == "ListarContasPagar":
            step_overrides[step.order] = {
                "filtrar_apenas_alteracao": "S",
                "filtrar_por_alteracao_de": since_br,
                "filtrar_por_alteracao_ate": until_br,
            }
        # Categorias / static-cadastro lookups don't need a date filter —
        # they're small, mostly stable, and full pull is fine.

    logger.info(
        "refresh_omie_pipeline_incremental pipeline=%s window=%s..%s steps_with_overrides=%s",
        pipeline_id, since_br, until_br, sorted(step_overrides.keys()),
    )

    return execute_pipeline(
        pipeline_id=pipeline_id,
        dry_run=False,
        param_overrides_by_step=step_overrides,
    )


@shared_task
def refresh_all_omie_pipelines():
    """Beat entrypoint: dispatch ``refresh_omie_pipeline_incremental``
    for every active pipeline whose name matches our Omie convention.

    Intentionally a separate task from each pipeline-specific run so
    Beat fires once and the per-pipeline jobs can be parallelised by
    the worker pool. If a pipeline is currently ``running``, skip it
    (avoids the 4-min Omie throttle that overlapping runs trigger).
    """
    from .models import ERPSyncPipeline, ERPSyncPipelineRun

    qs = ERPSyncPipeline.objects.filter(
        is_active=True,
        connection__provider__slug="omie",
    )

    dispatched: list[int] = []
    skipped: list[dict] = []
    for pipeline in qs:
        # Skip if a run is already in flight.
        if ERPSyncPipelineRun.objects.filter(
            pipeline=pipeline, status="running",
        ).exists():
            skipped.append({"pipeline_id": pipeline.id, "reason": "already_running"})
            continue
        refresh_omie_pipeline_incremental.delay(pipeline.id)
        dispatched.append(pipeline.id)

    logger.info(
        "refresh_all_omie_pipelines dispatched=%s skipped=%s",
        dispatched, skipped,
    )
    return {"dispatched": dispatched, "skipped": skipped}


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
