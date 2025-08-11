from django.contrib import admin
from django.apps import apps
from .models import *

# Get all models from the current app
app_models = apps.get_app_config('core').get_models()

# Register each model with the admin
for model in app_models:
    admin.site.register(model)