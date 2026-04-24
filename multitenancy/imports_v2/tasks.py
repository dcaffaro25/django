"""Celery tasks for the v2 import flow (Phase 6.z).

Moves the heavy analyze / commit work out of the request cycle so
gunicorn's 300s timeout can't bite on large imports. The web views
create the session with all inputs persisted, flip it to the
non-terminal status (``analyzing`` / ``committing``), and enqueue one
of these tasks; the frontend polls ``GET /sessions/<id>/`` until the
status leaves the non-terminal state.

Both tasks are idempotent on re-enqueue in practice:

  * ``analyze_session_task`` skips if the session has already left
    ``analyzing``.
  * ``commit_session_task`` skips if the session has already left
    ``committing``.

This matters because Celery's ``acks_late=False`` default doesn't
deduplicate retries — a worker that dies after saving terminal status
but before acking would re-pick the task on restart. Fast-path
bail-out keeps things safe.

In eager mode (``CELERY_TASK_ALWAYS_EAGER = True``, the dev/test
default when ``REDIS_URL`` is unset), ``.delay()`` runs the task body
inline in the caller's process — that's how the service-level sync
entry points stay backwards-compatible with existing tests.
"""
from __future__ import annotations

import logging
import traceback

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction

from multitenancy.models import ImportSession

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="imports_v2.analyze_session",
    ignore_result=True,
)
def analyze_session_task(self, session_pk: int) -> None:
    """Run the analyze body for a session already in ``ANALYZING``.

    Dispatches on ``session.mode`` and delegates to the mode-specific
    body function in ``services.py``. On unhandled exceptions the
    session is flipped to ``error`` with a traceback so the operator
    can see what went wrong via the session detail endpoint.

    Bail-out cases (return without doing work):

      * Session doesn't exist (deleted concurrently).
      * Session already left ``analyzing`` (previous run finished, or
        operator discarded mid-flight).
    """
    # Local import to dodge a circular dependency: services.py imports
    # this module when its async entry points call ``.delay()``.
    from . import services

    try:
        session = ImportSession.objects.get(pk=session_pk)
    except ImportSession.DoesNotExist:
        logger.warning(
            "analyze_session_task: session #%s does not exist", session_pk,
        )
        return

    if session.status != ImportSession.STATUS_ANALYZING:
        logger.info(
            "analyze_session_task: session #%s is %s, skipping",
            session.pk, session.status,
        )
        return

    try:
        if session.mode == ImportSession.MODE_ETL:
            services._run_analyze_etl(session)
        else:
            services._run_analyze_template(session)
    except SoftTimeLimitExceeded as exc:
        # Celery flagged the task for termination — soft limit fires
        # before the hard SIGKILL, giving us a last chance to mark
        # the session as error. Without this, the session would stay
        # in ``analyzing`` forever (the hard-kill cuts exception
        # handlers).
        logger.error(
            "analyze_session_task #%s hit soft time limit", session.pk,
        )
        _mark_session_error(session, exc, stage="analyze_timeout")
        raise
    except Exception as exc:
        logger.exception(
            "analyze_session_task #%s failed: %s", session.pk, exc,
        )
        _mark_session_error(session, exc, stage="analyze")
    finally:
        # Phase 6.z-g — clear the Redis live-progress key on terminal.
        # TTL would reap it eventually but explicit clear keeps the
        # key space tidy and avoids a stale read a fraction of a
        # second after the DB snapshot flips to ``done``.
        from . import progress_channel
        progress_channel.clear(session.pk)


@shared_task(
    bind=True,
    name="imports_v2.commit_session",
    ignore_result=True,
)
def commit_session_task(self, session_pk: int) -> None:
    """Run the commit body for a session already in ``COMMITTING``.

    The view is responsible for the gate check and the
    READY → COMMITTING transition; this task just runs the body. On
    unhandled exceptions ``_run_commit`` itself flips the session to
    ``error``, so our outer ``except`` is a belt-and-braces log.
    """
    from . import services

    try:
        session = ImportSession.objects.get(pk=session_pk)
    except ImportSession.DoesNotExist:
        logger.warning(
            "commit_session_task: session #%s does not exist", session_pk,
        )
        return

    if session.status != ImportSession.STATUS_COMMITTING:
        logger.info(
            "commit_session_task: session #%s is %s, skipping",
            session.pk, session.status,
        )
        return

    try:
        services._run_commit(session)
    except SoftTimeLimitExceeded as exc:
        # Same deal as analyze — soft limit fires first so we can
        # flip the session to error before the hard SIGKILL lands.
        # Keeps stuck sessions out of ``committing`` purgatory.
        logger.error(
            "commit_session_task #%s hit soft time limit", session.pk,
        )
        session.refresh_from_db()
        if session.status == ImportSession.STATUS_COMMITTING:
            _mark_session_error(session, exc, stage="commit_timeout")
        raise
    except Exception as exc:
        logger.exception(
            "commit_session_task #%s failed: %s", session.pk, exc,
        )
        # ``_run_commit`` already wrote the error status on most paths;
        # this is a safety net for bugs that skip that branch.
        session.refresh_from_db()
        if session.status == ImportSession.STATUS_COMMITTING:
            _mark_session_error(session, exc, stage="commit")
    finally:
        # Phase 6.z-g — clear the Redis live-progress key. Same
        # reasoning as analyze_session_task above.
        from . import progress_channel
        progress_channel.clear(session.pk)


@shared_task(
    name="imports_v2.reap_stale_sessions",
    ignore_result=True,
)
def reap_stale_sessions_task() -> dict:
    """Periodic beat task — flip non-terminal sessions older than the
    Celery hard time limit to ``error`` with a ``stage=timeout``
    diagnostic (Phase 6.z-f).

    Why: if a worker was SIGKILL'd, the container restarted, or the
    broker dropped a task mid-flight, the session stays in
    ``analyzing`` / ``committing`` forever — the frontend polls
    indefinitely and the operator has no recourse short of the
    discard endpoint.

    Cutoff = ``CELERY_TASK_TIME_LIMIT`` seconds past ``updated_at``
    plus a 60s grace buffer. The buffer means a task that's chewing
    right up to the limit doesn't get reaped on a second race
    condition.

    Returns a summary dict so the task log shows how many sessions
    were reaped on each tick.
    """
    from datetime import timedelta
    from django.conf import settings as dj_settings
    from django.utils import timezone

    hard_limit_s = int(
        getattr(dj_settings, "CELERY_TASK_TIME_LIMIT", 600) or 600
    )
    cutoff = timezone.now() - timedelta(seconds=hard_limit_s + 60)

    non_terminal = [
        ImportSession.STATUS_ANALYZING,
        ImportSession.STATUS_COMMITTING,
    ]
    stale = ImportSession.objects.filter(
        status__in=non_terminal, updated_at__lt=cutoff,
    )
    reaped_pks = list(stale.values_list("pk", flat=True))
    if not reaped_pks:
        return {"reaped": 0}

    with transaction.atomic():
        for session in ImportSession.objects.filter(pk__in=reaped_pks):
            # Re-check inside the transaction — the worker might have
            # finished between the query and the save.
            if session.status not in non_terminal:
                continue
            prior_status = session.status
            session.status = ImportSession.STATUS_ERROR
            session.result = {
                "error": (
                    f"Session stuck in {prior_status} past the task "
                    f"time limit ({hard_limit_s}s). Worker likely "
                    "crashed or restarted. Descarte e reinicie."
                ),
                "stage": "timeout",
                "type": "StaleSessionReaped",
                "prior_status": prior_status,
            }
            session.save(update_fields=["status", "result", "updated_at"])

    logger.warning(
        "reap_stale_sessions_task: reaped %d session(s): %s",
        len(reaped_pks), reaped_pks,
    )
    return {"reaped": len(reaped_pks), "session_pks": reaped_pks}


def _mark_session_error(
    session: ImportSession, exc: Exception, *, stage: str,
) -> None:
    """Write a terminal ``error`` status with traceback diagnostics.

    Wrapped in ``transaction.atomic`` so the status + result update
    goes in one shot — half-written error rows would confuse the
    frontend's polling loop.
    """
    with transaction.atomic():
        session.refresh_from_db()
        # Don't clobber an already-terminal status — another worker or
        # the body itself may have written a more precise diagnostic.
        if session.is_terminal():
            return
        session.status = ImportSession.STATUS_ERROR
        session.result = {
            "error": str(exc),
            "stage": stage,
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }
        session.save(update_fields=["status", "result", "updated_at"])
