from django.apps import AppConfig


class ApiMetaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api_meta"
    verbose_name = "API Meta / Introspection"
