from celery import shared_task
from .services.reconciliation_service import ReconciliationService
from .models import ReconciliationTask

@shared_task(bind=True)
def match_many_to_many_task(self, data, tenant_id=None):
    # Ensure a DB record exists for this task
    task_obj, created = ReconciliationTask.objects.get_or_create(
        task_id=self.request.id,
        defaults={
            "tenant_id": tenant_id,
            "parameters": data,
            "status": "PENDING",
        },
    )

    try:
        task_obj.status = "STARTED"
        task_obj.save(update_fields=["status", "updated_at"])

        result = ReconciliationService.match_many_to_many_with_set2(data, tenant_id)

        task_obj.status = "SUCCESS"
        task_obj.result = result
        task_obj.save(update_fields=["status", "result", "updated_at"])
        return result

    except Exception as e:
        task_obj.status = "FAILURE"
        task_obj.error_message = str(e)
        task_obj.save(update_fields=["status", "error_message", "updated_at"])
        raise
