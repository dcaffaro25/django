# NORD/multitenancy/apps.py

from django.apps import AppConfig

class MultitenancyConfig(AppConfig):
    name = 'multitenancy'

    def ready(self):
        import multitenancy.signals
        # Importing the checks module registers the ``@register``'d
        # functions with Django's system-check framework. No-op when
        # no checks fire (i.e. healthy config).
        import multitenancy.checks  # noqa: F401
