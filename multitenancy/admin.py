from django.contrib import admin
from django.apps import apps
from .models import *

# Get all models from the current app
app_models = apps.get_app_config('multitenancy').get_models()


    
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "subdomain", "created_at")
    search_fields = ("name", "subdomain", "id")

@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company")
    list_filter = ("company",)
    search_fields = ("name", "id")

#@admin.register(CustomUser)
#class CustomUserAdmin(UserAdmin):
    # keep your fields config; ensure search_fields present:
#    search_fields = ("username", "email", "first_name", "last_name", "id")
    
# Register each model with the admin
#for model in app_models:
#    admin.site.register(model)