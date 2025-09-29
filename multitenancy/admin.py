# multitenancy/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .models import Company, Entity  # adjust imports to your actual models

User = get_user_model()

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "subdomain", "created_at")
    search_fields = ("name", "subdomain", "id")
    list_filter = ("created_at",)
    # if you also use autocomplete to Company somewhere else:
    # date_hierarchy = "created_at"

@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company")
    search_fields = ("name", "id", "company__name")
    list_filter = ("company",)
    autocomplete_fields = ("company",)

# Ensure the User admin has search_fields (for ReconciliationConfig.user autocomplete)
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # keep the default fieldsets/behavior from UserAdmin but add good search fields
    search_fields = ("username", "email", "first_name", "last_name", "id")
    list_display = ("id", "username", "email", "is_active", "is_staff", "is_superuser")
