import os
from celery import Celery

# Default settings for Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")

app = Celery("nord_backend")

# Load settings from Django settings, prefixed with "CELERY_"
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py from all installed apps
app.autodiscover_tasks()

broker_connection_retry_on_startup = True