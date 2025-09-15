from celery import shared_task
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask

@shared_task(bind=True)
def match_many_to_many_task(self, db_id, data, tenant_id=None, auto_match_100=False):
    """
    Background reconciliation task.
    Updates the ReconciliationTask row instead of creating a new one.
    """
    task_obj = ReconciliationTask.objects.get(id=db_id)

    try:
        task_obj.status = "running"
        task_obj.save(update_fields=["status", "updated_at"])

        result = ReconciliationService.match_many_to_many_with_set2(data, tenant_id, auto_match_100=auto_match_100)

        task_obj.status = "completed"
        task_obj.result = result
        task_obj.save(update_fields=["status", "result", "updated_at"])
        return result

    except Exception as e:
        task_obj.status = "failed"
        task_obj.error_message = str(e)
        task_obj.save(update_fields=["status", "error_message", "updated_at"])
        raise
