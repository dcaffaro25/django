from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        from . import admin_autoregister  # noqa: F401
        from . import celery_hooks  # noqa: F401
        # Wire error capture: Django 500 signal + Celery failure.
        from . import error_signals  # noqa: F401