# NORD/multitenancy/apps.py

from django.apps import AppConfig

class MultitenancyConfig(AppConfig):
    name = 'multitenancy'

    def ready(self):
        import multitenancy.signals
