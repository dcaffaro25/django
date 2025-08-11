from django.apps import AppConfig

#def ready(self):
#    import accounting.signals
    
class AccountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounting'
