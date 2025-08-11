from django.contrib import admin
from django.apps import apps
from .models import *

# Get all models from the current app
app_models = apps.get_app_config('accounting').get_models()

class TransactionAdmin(admin.ModelAdmin):
    list_per_page = 500
    
admin.site.register(Transaction, TransactionAdmin)

class BankTransactionAdmin(admin.ModelAdmin):
    list_per_page = 500
    
admin.site.register(BankTransaction, BankTransactionAdmin)

# Register each model with the admin
for model in app_models:
    try:
        admin.site.register(model)
    except:
        print(f'{model} already registered')
    
