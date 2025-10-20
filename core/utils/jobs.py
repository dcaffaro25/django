# jobs/utils.py
from typing import Optional, Dict, Any
from django.db.models import F
from core.models import Job
from core.constants import STATE_MAP

def job_progress(task, *, done: int, total: Optional[int] = None,
                 by_category: Optional[Dict[str, int]] = None,
                 meta: Optional[Dict[str, Any]] = None):
    """
    Set state=PROGRESS + update counters.
    Safe to call frequently (once per batch/chunk).
    """
    task_id = getattr(task.request, "id", None)
    if not task_id:
        return
    updates = {"state": STATE_MAP["PROGRESS"], "done": done}
    if total is not None:
        updates["total"] = total
    if by_category is not None:
        updates["by_category"] = by_category
    if meta is not None:
        updates["meta"] = meta
    Job.objects.filter(task_id=task_id).update(**updates)
