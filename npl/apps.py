from django.apps import AppConfig


class NplConfig(AppConfig):
    """Configuration for the NPL application."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'npl'
    verbose_name = 'NPL'
    
    def ready(self):
        # importa os signals para registrar os handlers
        import npl.signals  # noqa
