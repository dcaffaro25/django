# jobs/celery_hooks.py
from datetime import datetime, timezone
from celery import signals
from .models import Job
from .constants import STATE_MAP

def _utcnow():
    return datetime.now(tz=timezone.utc)

@signals.after_task_publish.connect
def job_after_publish(sender=None, headers=None, body=None, **kwargs):
    task_id = headers.get("id") if headers else None
    task_name = headers.get("task") if headers else sender
    queue = (headers or {}).get("reply_to") or kwargs.get("routing_key")
    kind  = (headers or {}).get("job_kind") or task_name or "other"
    tenant_id = (headers or {}).get("tenant_id")
    if not task_id:
        return
    Job.objects.update_or_create(
        task_id=task_id,
        defaults=dict(
            task_name=task_name or "",
            queue=queue,
            kind=str(kind)[:64],
            tenant_id=tenant_id,
            state=STATE_MAP["SENT"],
            enqueued_at=_utcnow(),
        ),
    )

@signals.task_received.connect
def job_on_received(sender=None, request=None, **kwargs):
    if not request:
        return
    Job.objects.filter(task_id=request.id).update(state=STATE_MAP["RECEIVED"])

@signals.task_prerun.connect
def job_on_prerun(task_id=None, task=None, **kwargs):
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["STARTED"],
        started_at=_utcnow(),
        worker=getattr(task.request, "hostname", None),
    )

@signals.task_retry.connect
def job_on_retry(request=None, **kwargs):
    if not request:
        return
    Job.objects.filter(task_id=request.id).update(
        state=STATE_MAP["RETRY"],
        retries=request.retries or 0,
        max_retries=getattr(request, "max_retries", 0) or 0,
    )

@signals.task_success.connect
def job_on_success(sender=None, result=None, **kwargs):
    task_id = getattr(sender.request, "id", None)
    if not task_id:
        return
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["SUCCESS"],
        finished_at=_utcnow(),
        result=result if isinstance(result, (dict, list)) else {"result": result},
    )

@signals.task_failure.connect
def job_on_failure(task_id=None, exception=None, traceback=None, **kwargs):
    Job.objects.filter(task_id=task_id).update(
        state=STATE_MAP["FAILURE"],
        finished_at=_utcnow(),
        error=str(exception) if exception else None,
        meta={"traceback": traceback} if traceback else None,
    )

@signals.task_revoked.connect
def job_on_revoked(request=None, terminated=None, signum=None, expired=None, **kwargs):
    if not request:
        return
    Job.objects.filter(task_id=request.id).update(
        state=STATE_MAP["REVOKED"],
        finished_at=_utcnow(),
        meta={"terminated": terminated, "signum": signum, "expired": expired},
    )
