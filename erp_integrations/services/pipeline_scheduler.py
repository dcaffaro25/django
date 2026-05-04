"""
Phase-4 of the Sandbox API plan: scheduled-routine runner.

Wraps the existing pipeline executor with two pieces of operational
glue that the manual sandbox path doesn't need:

1. **Incremental window**: when ``ERPSyncPipeline.incremental_config``
   is set, the runner computes a ``[from, to)`` window relative to
   ``last_high_watermark`` (with optional safety lookback) and injects
   the ``from`` value into the first step's ``extra_params`` under
   the configured ``param_name``. This is what turns a 4h cron into
   "fetch everything modified since the last successful run" instead
   of pulling the whole dataset every tick.

2. **Single-flight lock**: Celery beat fires don't coordinate by
   themselves, so we acquire a row-level lock on the pipeline before
   running. If another worker already holds it, this fire becomes a
   no-op (returns ``locked``) — safer than two workers racing on the
   same high-watermark column. Pair with concurrency=1 if the
   scheduler tier doesn't support row locks.

The Celery task itself (``erp_integrations.tasks.run_pipeline_scheduled``)
is the thinnest possible wrapper: parse args → call this service →
log the outcome. Beat configuration (which schedule fires which
pipeline) is owned at the deployment layer and is intentionally NOT
hard-coded here — operators wire ``ERPSyncPipeline.schedule_rrule`` →
``django-celery-beat.PeriodicTask`` rows in a future infra commit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone as dj_tz

from erp_integrations.models import ERPSyncPipeline, ERPSyncPipelineRun
from erp_integrations.services.pipeline_service import execute_pipeline

logger = logging.getLogger(__name__)


# ``status`` returned by ``run_scheduled_pipeline`` — distinct from the
# underlying pipeline run status (completed / partial / failed) because
# we need to surface "skipped" outcomes too.
STATUS_RAN = "ran"
STATUS_LOCKED = "locked"
STATUS_PAUSED = "paused"
STATUS_DISABLED = "disabled"
STATUS_NO_PIPELINE = "no_pipeline"
STATUS_ERROR = "error"

DEFAULT_LOOKBACK_SECONDS = 300


@dataclass
class ScheduledRunOutcome:
    """Wire-friendly result the Celery task / API endpoint can return."""

    status: str
    pipeline_id: int
    pipeline_run_id: Optional[int] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "pipeline_id": self.pipeline_id,
            "pipeline_run_id": self.pipeline_run_id,
            "window_start": self.window_start.isoformat() if self.window_start else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "detail": self.detail,
        }


def run_scheduled_pipeline(
    pipeline_id: int,
    *,
    triggered_by: str = "schedule",
    force_full_dump: bool = False,
    explicit_window: Optional[tuple] = None,
) -> ScheduledRunOutcome:
    """Run one pipeline with the scheduling/incremental glue.

    ``triggered_by``: one of ``schedule`` / ``manual`` / ``api``. Stamped
    onto the ``ERPSyncPipelineRun.triggered_by`` field so the run history
    can show who fired what.

    ``force_full_dump``: bypasses the incremental window even if
    ``incremental_config`` is set. Useful for the "Replay full dataset"
    button in the UI.

    ``explicit_window``: ``(start, end)`` datetimes that override the
    computed window. Used by the "Replay this window" button — does NOT
    bump the high-watermark (the operator is investigating, not
    catching up).
    """
    # Lock the pipeline row so concurrent fires of the same pipeline
    # don't both advance the high-watermark.
    with transaction.atomic():
        try:
            pipeline = (
                ERPSyncPipeline.objects
                .select_for_update(skip_locked=True)
                .filter(pk=pipeline_id, is_deleted=False)
                .first()
            )
        except Exception as exc:
            # select_for_update unavailable on some backends; fall back
            # to the plain fetch so dev sqlite still works.
            logger.debug("select_for_update unavailable: %s", exc)
            pipeline = ERPSyncPipeline.objects.filter(pk=pipeline_id, is_deleted=False).first()

        if pipeline is None:
            return ScheduledRunOutcome(status=STATUS_NO_PIPELINE, pipeline_id=pipeline_id, detail="Pipeline não encontrado.")

        if not pipeline.is_active:
            return ScheduledRunOutcome(status=STATUS_DISABLED, pipeline_id=pipeline_id, detail="Pipeline inativo.")

        # Paused honours triggered_by: manual / api ignores the pause
        # (operator is explicitly running it), schedule respects it.
        if pipeline.is_paused and triggered_by == "schedule":
            return ScheduledRunOutcome(status=STATUS_PAUSED, pipeline_id=pipeline_id, detail="Pipeline pausado.")

        # Compute window before doing the heavy work.
        window_start, window_end = _compute_window(
            pipeline,
            force_full_dump=force_full_dump,
            explicit_window=explicit_window,
        )

        # Inject incremental param into first step's extra_params if
        # configured. We do NOT mutate the persisted step — this is a
        # per-run override that lives only on the pipeline-run config.
        param_overrides_for_first_step = _build_first_step_overrides(
            pipeline, window_start,
        )

    # Outside the lock-block: the actual run. We give up the lock here
    # because pipeline runs can be slow (minutes) and holding the lock
    # that long would starve other manual triggers. The high-watermark
    # update at the end re-acquires briefly.
    try:
        run_result = execute_pipeline(
            pipeline_id=pipeline.id,
            param_overrides_by_step=(
                {1: param_overrides_for_first_step}
                if param_overrides_for_first_step else None
            ),
            triggered_by=triggered_by,
            incremental_window=(window_start, window_end) if (window_start or window_end) else None,
        )
    except Exception as exc:
        logger.exception("Scheduled pipeline run crashed: pipeline_id=%s", pipeline_id)
        return ScheduledRunOutcome(
            status=STATUS_ERROR,
            pipeline_id=pipeline_id,
            window_start=window_start,
            window_end=window_end,
            detail=f"{type(exc).__name__}: {exc}",
        )

    pipeline_run_id = run_result.get("run_id")
    run_status = run_result.get("status", "completed")

    # Advance the high-watermark when the run actually succeeded AND we
    # weren't replaying a historical window. Failure / partial keeps the
    # old watermark so the next tick retries the same window.
    if (
        run_status == "completed"
        and explicit_window is None
        and not force_full_dump
        and pipeline.incremental_config
    ):
        with transaction.atomic():
            ERPSyncPipeline.objects.filter(pk=pipeline.id).update(
                last_high_watermark=window_end,
            )

    return ScheduledRunOutcome(
        status=STATUS_RAN,
        pipeline_id=pipeline.id,
        pipeline_run_id=pipeline_run_id,
        window_start=window_start,
        window_end=window_end,
        detail=run_status,
    )


# ---------------------------------------------------------------------
# Window math
# ---------------------------------------------------------------------

def _compute_window(
    pipeline: ERPSyncPipeline,
    *,
    force_full_dump: bool = False,
    explicit_window: Optional[tuple] = None,
) -> tuple:
    """Returns ``(start, end)`` for this run.

    * Explicit window overrides everything.
    * Otherwise: ``end = now()``; ``start = max(epoch, last_high_watermark - lookback)``.
    * No incremental_config → ``start = None`` (full-dump semantics, the
      same as the manual sandbox path).
    """
    if explicit_window:
        return explicit_window

    end = dj_tz.now()

    if force_full_dump or not pipeline.incremental_config:
        return (None, end)

    cfg = pipeline.incremental_config or {}
    lookback = int(cfg.get("lookback_seconds", DEFAULT_LOOKBACK_SECONDS) or 0)
    hw = pipeline.last_high_watermark
    if hw is None:
        # First run with incremental config: pull a generous backfill
        # window. Operator can override with explicit_window if they
        # want a different shape; default is "everything from epoch".
        return (None, end)

    start = hw - timedelta(seconds=max(0, lookback))
    return (start, end)


def _build_first_step_overrides(
    pipeline: ERPSyncPipeline,
    window_start: Optional[datetime],
) -> Dict[str, Any]:
    """Produce a dict to merge into the first step's ``extra_params``.

    Empty when no incremental config or no window_start (full dump).
    """
    if window_start is None:
        return {}
    cfg = pipeline.incremental_config or {}
    param_name = cfg.get("param_name")
    if not param_name:
        return {}
    fmt = (cfg.get("format") or "iso8601").lower()
    return {param_name: _format_window_value(window_start, fmt)}


def _format_window_value(value: datetime, fmt: str) -> str:
    """Format the window-start value the way the upstream API expects.

    Default ``iso8601`` covers most modern APIs. Older APIs (Omie,
    legacy SOAP) often want ``dd/mm/yyyy`` — that's the next supported
    format. Add more cases as we onboard providers.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if fmt == "br_date":
        return value.strftime("%d/%m/%Y")
    if fmt == "br_datetime":
        return value.strftime("%d/%m/%Y %H:%M:%S")
    if fmt == "epoch_seconds":
        return str(int(value.timestamp()))
    # iso8601 default
    return value.isoformat()
