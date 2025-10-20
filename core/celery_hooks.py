# jobs/celery_hooks.py
from datetime import datetime, timezone
from django.apps import apps
from celery.signals import (
    after_task_publish, task_prerun, task_success,
    task_failure, task_retry, task_revoked,
)
from .models import Job
from .constants import STATE_MAP
from django.utils.timezone import now
from typing import Optional, Union


def _header(headers, key, default=None):
    try:
        return (headers or {}).get(key, default)
    except Exception:
        return default

def _safe_json(obj):
    try:
        json.dumps(obj)
        return obj
    except Exception:
        # last resort so we can still show something in the UI
        return {"repr": repr(obj)}

@after_task_publish.connect
def job_after_publish(sender=None, headers=None, body=None, **kwargs):
    task_id = _header(headers, "id") or kwargs.get("task_id")
    if not task_id:
        return
    Job.objects.update_or_create(
        task_id=task_id,
        defaults={
            "task_name": sender or "",
            "state": STATE_MAP["SENT"],
            "kind": _header(headers, "job_kind", sender or "other"),
            "tenant_id": _header(headers, "tenant_id"),
            "created_by_id": _header(headers, "user_id"),
            "queue": (kwargs.get("routing_key") or
                      (kwargs.get("properties") or {}).get("delivery_info", {}).get("routing_key")),
            "enqueued_at": now(),
        },
    )

@task_prerun.connect
def job_task_prerun(sender=None, task_id=None, task=None, **kwargs):
    req = getattr(task, "request", None)
    headers = getattr(req, "headers", {}) if req else {}
    Job.objects.update_or_create(
        task_id=task_id,
        defaults={
            "task_name": sender.name if sender else "",
            "kind": _header(headers, "job_kind", sender.name if sender else "other"),
            "tenant_id": _header(headers, "tenant_id"),
            "created_by_id": _header(headers, "user_id"),
        },
    )
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["STARTED"],
        started_at=now(),
        worker=getattr(req, "hostname", None),
        queue=getattr(req, "routing_key", None),
        retries=getattr(req, "retries", 0),
        max_retries=getattr(req, "max_retries", 0),
        priority=(getattr(req, "delivery_info", {}) or {}).get("priority"),
        eta=getattr(req, "eta", None),
        expires=getattr(req, "expires", None),
    )

@task_retry.connect
def job_task_retry(sender=None, request=None, reason=None, einfo=None, **kwargs):
    if not request:
        return
    Job.objects.filter(task_id=request.id).update(
        state=STATE_MAP["RETRY"],
        retries=getattr(request, "retries", 0),
    )

@task_success.connect
def job_task_success(sender=None, result=None, task_id=None, **kwargs):
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["SUCCESS"],
        finished_at=now(),
        result=_safe_json(result),
    )

@task_failure.connect
def job_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["FAILURE"],
        finished_at=now(),
        error=str(exception) if exception else None,
    )

@task_revoked.connect
def job_task_revoked(sender=None, request=None, terminated=None, signum=None, expired=None, **kwargs):
    if not request:
        return
    Job.objects.filter(task_id=request.id).update(
        state=STATE_MAP["REVOKED"],
        finished_at=now(),
        error="revoked",
    )