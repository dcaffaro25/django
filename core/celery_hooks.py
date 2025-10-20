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



# Prefer an unscoped manager if your model exposes one (recommended)
JOB_QS = getattr(Job, "all_objects", None) or Job.objects   # all_objects should be a plain models.Manager()

Company = apps.get_model("multitenancy", "Company")


def _header(headers, key, default=None):
    try:
        return (headers or {}).get(key, default)
    except Exception:
        return default


def _extract_tenant_id(headers, request=None):
    """
    Pull company/tenant from Celery headers first;
    fall back to request headers if present.
    """
    tid = _header(headers, "tenant_id") or _header(headers, "company_id")
    if tid:
        return tid
    if request:
        h = getattr(request, "headers", {}) or {}
        tid = h.get("tenant_id") or h.get("company_id")
    return tid


def _update_or_create_job(task_id: str, company_id: str | int | None, **defaults):
    """
    Upsert a Job row with tenant scoping. If company_id is missing, we still
    save a record keyed only by task_id (useful for late headers), but you
    should strive to always pass tenant_id when applying tasks.
    """
    lookup = {"task_id": task_id}
    if company_id:
        lookup["company_id"] = company_id
        defaults.setdefault("company_id", company_id)
    JOB_QS.update_or_create(**lookup, defaults=defaults)


def _update_job(task_id: str, company_id: str | int | None, **fields):
    """
    Update with tenant scope when we have it; otherwise update by task_id only.
    """
    qs = JOB_QS.filter(task_id=task_id)
    if company_id:
        qs = qs.filter(company_id=company_id)
    qs.update(**fields)


@after_task_publish.connect
def job_after_publish(sender=None, headers=None, body=None, **kwargs):
    task_id = _header(headers, "id") or kwargs.get("task_id")
    if not task_id:
        return

    tenant_id = _extract_tenant_id(headers)
    kind = _header(headers, "job_kind", sender or "")
    queue = (
        kwargs.get("routing_key")
        or (kwargs.get("properties") or {}).get("delivery_info", {}).get("routing_key")
    )

    _update_or_create_job(
        task_id,
        tenant_id,
        task_name=(sender or ""),
        state=STATE_MAP["SENT"],
        kind=kind,
        queue=queue,
        enqueued_at=now(),
    )


@task_prerun.connect
def job_task_prerun(sender=None, task_id=None, task=None, **kwargs):
    req = getattr(task, "request", None)
    headers = getattr(req, "headers", {}) if req else {}
    tenant_id = _extract_tenant_id(headers, request=req)
    kind = _header(headers, "job_kind", sender.name if sender else "")
    worker = getattr(req, "hostname", None)
    retries = getattr(req, "retries", 0)
    queue = getattr(req, "routing_key", None)

    _update_or_create_job(
        task_id,
        tenant_id,
        task_name=(sender.name if sender else ""),
        kind=kind,
    )
    _update_job(
        task_id,
        tenant_id,
        state=STATE_MAP["STARTED"],
        started_at=now(),
        worker=worker,
        queue=queue,
        retries=retries,
    )


@task_retry.connect
def job_task_retry(sender=None, request=None, reason=None, einfo=None, **kwargs):
    if not request:
        return
    tenant_id = _extract_tenant_id(getattr(request, "headers", {}), request=request)
    _update_job(
        request.id,
        tenant_id,
        state=STATE_MAP["RETRY"],
        retries=getattr(request, "retries", 0),
    )


@task_success.connect
def job_task_success(sender=None, result=None, task_id=None, **kwargs):
    # No headers on this signal; update by task_id alone
    _update_job(
        task_id,
        company_id=None,
        state=STATE_MAP["SUCCESS"],
        finished_at=now(),
        result=result,
    )


@task_failure.connect
def job_task_failure(sender=None, task_id=None, exception=None, einfo=None, **kwargs):
    _update_job(
        task_id,
        company_id=None,
        state=STATE_MAP["FAILURE"],
        finished_at=now(),
        error=str(exception) if exception else None,
    )


@task_revoked.connect
def job_task_revoked(sender=None, request=None, terminated=None, signum=None, expired=None, **kwargs):
    if not request:
        return
    _update_job(
        request.id,
        company_id=None,
        state=STATE_MAP["REVOKED"],
        finished_at=now(),
        error="revoked",
    )