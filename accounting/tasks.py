from celery import shared_task
import time

@shared_task
def demo_add(x, y):
    time.sleep(10)
    return x + y
