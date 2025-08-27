from django.http import JsonResponse
from celery.result import AsyncResult
#from .tasks import demo_add

from celery import shared_task
from .models import BankTransaction, JournalEntry
from .views import BankTransactionViewSet




def start_task(request):
    # enqueue background job
    task = demo_add.delay(40, 2)
    return JsonResponse({
        "task_id": task.id,
        "status": task.status,
    })


def task_status(request, task_id: str):
    # check status/result
    res = AsyncResult(task_id)
    return JsonResponse({
        "task_id": task_id,
        "status": res.status,
        "result": res.result if res.ready() else None,
    })
