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
    except Exception as exc:
        logger.exception(
            "analyze_session_task #%s failed: %s", session.pk, exc,
        )
        _mark_session_error(session, exc, stage="analyze")


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
    except Exception as exc:
        logger.exception(
            "commit_session_task #%s failed: %s", session.pk, exc,
        )
        # ``_run_commit`` already wrote the error status on most paths;
        # this is a safety net for bugs that skip that branch.
        session.refresh_from_db()
        if session.status == ImportSession.STATUS_COMMITTING:
            _mark_session_error(session, exc, stage="commit")


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
