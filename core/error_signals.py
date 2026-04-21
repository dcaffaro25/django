"""Wire error capture to Django + Celery signals.

Imported from ``CoreConfig.ready()``. Both handlers swallow all
exceptions internally — a capture failure must never cascade
into the original request/task's error path.
"""

from __future__ import annotations

import logging

from celery.signals import task_failure
from django.core.signals import got_request_exception
from django.dispatch import receiver


log = logging.getLogger(__name__)


@receiver(got_request_exception)
def _on_django_exception(sender, request=None, **kwargs):
    """Catches anything that slips past the DRF exception handler
    (plain Django views, middleware, etc.)."""
    try:
        import sys
        from core.models import ErrorReport
        from core.services.error_capture import capture_exception

        exc_type, exc, _tb = sys.exc_info()
        if exc is None:
            return
        capture_exception(exc, kind=ErrorReport.KIND_BACKEND_DJANGO, request=request)
    except Exception:  # pragma: no cover — defensive
        log.exception("error_signals: got_request_exception capture failed")


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    """Celery task_failure → ErrorReport(kind='celery')."""
    try:
        from core.models import ErrorReport
        from core.services.error_capture import capture_exception

        if exception is None:
            return
        task_name = getattr(sender, "name", "") or ""
        capture_exception(exception, kind=ErrorReport.KIND_CELERY, task_name=task_name)
    except Exception:  # pragma: no cover
        log.exception("error_signals: task_failure capture failed")
