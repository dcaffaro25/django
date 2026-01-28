from django.apps import AppConfig


class ErpIntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "erp_integrations"
    verbose_name = "ERP Integrations"

    def ready(self):
        # Ensure our admin is loaded so ERP* models appear in Django admin.
        # Unregister first in case core.admin_autoregister already registered them.
        from django.contrib import admin
        from django.contrib.admin.sites import NotRegistered

        from .models import ERPAPIDefinition, ERPConnection, ERPProvider

        for model in (ERPProvider, ERPConnection, ERPAPIDefinition):
            try:
                admin.site.unregister(model)
            except NotRegistered:
                pass
        from . import admin as _admin  # noqa: F401  # registers with our custom ModelAdmins
