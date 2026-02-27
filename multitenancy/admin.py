# multitenancy/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from .models import Company, Entity, SubstitutionRule  # adjust imports to your actual models
from django.contrib.admin.utils import model_ngettext
from django.contrib.admin.views.main import ChangeList
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib.admin import SimpleListFilter

User = get_user_model()


def _is_tenant_scoped_model(related_model):
    """Return True if the model has a company ForeignKey (tenant-scoped)."""
    try:
        f = related_model._meta.get_field("company")
        return isinstance(f, models.ForeignKey)
    except (FieldDoesNotExist, AttributeError):
        return False


class CompanyFKFilterMixin:
    """
    Filters FK combobox options for tenant-scoped related models based on the
    selected company. When editing an existing object, options are filtered by
    obj.company. When adding, ?company=<id> in the URL can pre-filter options.
    """
    def formfield_for_foreignkey(self, db_field, request, obj=None, **kwargs):
        if db_field.name == "company":
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if not hasattr(self.model, "company"):
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        related_model = getattr(db_field, "remote_field", None) and db_field.remote_field.model
        if not related_model or not _is_tenant_scoped_model(related_model):
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        company_id = None
        if obj is not None and obj.pk and hasattr(obj, "company_id"):
            company_id = obj.company_id
        if company_id is None:
            resolver_kwargs = getattr(getattr(request, "resolver_match", None), "kwargs", None) or {}
            pk = resolver_kwargs.get("object_id")
            if pk and hasattr(self.model, "company"):
                try:
                    company_id = self.model.objects.filter(pk=pk).values_list("company_id", flat=True).first()
                except (TypeError, ValueError):
                    pass
        if company_id is None:
            company_id = request.GET.get("company")
            if company_id:
                try:
                    company_id = int(company_id)
                except (TypeError, ValueError):
                    company_id = None

        if company_id is not None:
            kwargs["queryset"] = db_field.remote_field.model.objects.filter(company_id=company_id)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, obj=None, **kwargs):
        if not hasattr(self.model, "company"):
            return super().formfield_for_manytomany(db_field, request, **kwargs)

        related_model = getattr(db_field, "remote_field", None) and getattr(db_field.remote_field, "model", None)
        if not related_model or not _is_tenant_scoped_model(related_model):
            return super().formfield_for_manytomany(db_field, request, **kwargs)

        company_id = None
        if obj is not None and obj.pk and hasattr(obj, "company_id"):
            company_id = obj.company_id
        if company_id is None:
            resolver_kwargs = getattr(getattr(request, "resolver_match", None), "kwargs", None) or {}
            pk = resolver_kwargs.get("object_id")
            if pk and hasattr(self.model, "company"):
                try:
                    company_id = self.model.objects.filter(pk=pk).values_list("company_id", flat=True).first()
                except (TypeError, ValueError):
                    pass
        if company_id is None:
            company_id = request.GET.get("company")
            if company_id:
                try:
                    company_id = int(company_id)
                except (TypeError, ValueError):
                    company_id = None

        if company_id is not None:
            kwargs["queryset"] = db_field.remote_field.model.objects.filter(company_id=company_id)

        return super().formfield_for_manytomany(db_field, request, **kwargs)

class FastDeleteMixin:
    """
    Mixin to replace Django's default 'delete_selected' action with a fast
    deletion that avoids a confirmation page.
    """
    @admin.action(description="Delete selected records")
    def fast_delete_selected(self, request, queryset):
        count = queryset.count()
        if count:
            queryset.delete()
            self.message_user(
                request,
                f"Successfully deleted {count} {model_ngettext(self.model, count)}."
            )

    # Register our custom action; removing get_actions avoids bound‑method errors
    actions = ['fast_delete_selected']

class AuditColsMixin:
    """
    Mixin to add standard audit columns (created/updated) to ModelAdmin classes.
    It dynamically appends these fields to list_display, list_filter,
    readonly_fields, date_hierarchy and uses select_related to avoid N+1 queries.
    """

    AUDIT_FIELDS = ["created_at", "created_by", "updated_at", "updated_by"]

    # -- Column methods ------------------------------------------------
    def created_at_col(self, obj):
        return obj.created_at
    created_at_col.admin_order_field = "created_at"
    created_at_col.short_description = _("Created at")

    def updated_at_col(self, obj):
        return obj.updated_at
    updated_at_col.admin_order_field = "updated_at"
    updated_at_col.short_description = _("Updated at")

    def created_by_col(self, obj):
        return obj.created_by
    created_by_col.admin_order_field = "created_by__username"
    created_by_col.short_description = _("Created by")

    def updated_by_col(self, obj):
        return obj.updated_by
    updated_by_col.admin_order_field = "updated_by__username"
    updated_by_col.short_description = _("Updated by")

    # -- Admin API overrides ------------------------------------------
    def get_list_display(self, request):
        # Start with the default list_display
        columns = list(super().get_list_display(request))
        # Append audit columns only if the model has them
        for field in self.AUDIT_FIELDS:
            if hasattr(self.model, field):
                col_name = f"{field}_col"
                if col_name not in columns:
                    columns.append(col_name)
        return tuple(columns)

    def get_list_filter(self, request):
        # Include audit fields in filters
        filters = list(super().get_list_filter(request))
        for field in self.AUDIT_FIELDS:
            if hasattr(self.model, field) and field not in filters:
                filters.append(field)
        return tuple(filters)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        for field in self.AUDIT_FIELDS:
            if hasattr(self.model, field) and field not in readonly:
                readonly.append(field)
        return tuple(readonly)

    def get_date_hierarchy(self, request):
        # Use created_at for date hierarchy if present
        if hasattr(self.model, "created_at"):
            return "created_at"
        return super().get_date_hierarchy(request)

    def get_queryset(self, request):
        # Use select_related to prefetch user fields
        qs = super().get_queryset(request)
        user_fields = []
        if hasattr(self.model, "created_by"):
            user_fields.append("created_by")
        if hasattr(self.model, "updated_by"):
            user_fields.append("updated_by")
        return qs.select_related(*user_fields)

class PerPageFilter(SimpleListFilter):
    title = "rows per page"
    parameter_name = "per_page"

    def lookups(self, request, model_admin):
        return [(str(n), str(n)) for n in (25, 50, 100, 200, 500, 1000)]

    def queryset(self, request, queryset):
        return queryset  # no filtering; just adds the parameter



class CompanyScopedAdmin(CompanyFKFilterMixin, FastDeleteMixin, AuditColsMixin, admin.ModelAdmin):
    list_per_page = 100
    list_max_show_all = 5000

    def get_list_per_page(self, request):
        # Honour ?per_page=... in the URL
        value = request.GET.get("per_page")
        if value:
            try:
                per_page = int(value)
                if 10 <= per_page <= 1000:
                    key = f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
                    request.session[key] = per_page
                    return per_page
            except (ValueError, TypeError):
                pass
        # Otherwise fall back to session or default
        key = f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
        return request.session.get(key, self.list_per_page)

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        filters.append(PerPageFilter)
        return filters

class PlainAdmin(FastDeleteMixin, AuditColsMixin, admin.ModelAdmin):
    list_per_page = 100
    list_max_show_all = 5000

    def get_list_per_page(self, request):
        value = request.GET.get("per_page")
        if value:
            try:
                per_page = int(value)
                if 10 <= per_page <= 1000:
                    key = f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
                    request.session[key] = per_page
                    return per_page
            except (ValueError, TypeError):
                pass
        key = f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
        return request.session.get(key, self.list_per_page)

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        filters.append(PerPageFilter)
        return filters

@admin.register(Company)
class CompanyAdmin(PlainAdmin):
    list_display = ("id", "name", "subdomain", "notes", "created_at")
    search_fields = ("name", "subdomain", "id", "notes")
    list_filter = ("created_at", "notes")
    # if you also use autocomplete to Company somewhere else:
    # date_hierarchy = "created_at"

@admin.register(Entity)
class EntityAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "company", "notes")
    search_fields = ("name", "id", "company__name", "notes")
    list_filter = ("company", "notes")
    autocomplete_fields = ("company",)


def _filter_conditions_preview(obj, max_len=80):
    if not obj.filter_conditions:
        return "-"
    import json
    s = json.dumps(obj.filter_conditions, sort_keys=True)
    return s[:max_len] + "…" if len(s) > max_len else s


# Unregister if auto-registered, then register our custom SubstitutionRule admin
try:
    admin.site.unregister(SubstitutionRule)
except admin.sites.NotRegistered:
    pass


@admin.register(SubstitutionRule)
class SubstitutionRuleAdmin(CompanyScopedAdmin):
    list_display = (
        "id",
        "title",
        "model_name",
        "field_name",
        "match_type",
        "match_value",
        "substitution_value",
        "company",
        "filter_conditions_preview",
        "is_deleted",
        "notes",
    )
    list_filter = ("company", "model_name", "field_name", "match_type", "is_deleted")
    search_fields = (
        "title",
        "model_name",
        "field_name",
        "match_value",
        "substitution_value",
        "notes",
    )
    list_select_related = ("company", "created_by", "updated_by")
    autocomplete_fields = ("company",)
    raw_id_fields = ("created_by", "updated_by")
    ordering = ("company", "model_name", "field_name", "id")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "company",
                    "model_name",
                    "field_name",
                    "match_type",
                    "match_value",
                    "substitution_value",
                    "filter_conditions",
                    "notes",
                ),
            },
        ),
        (
            _("Audit"),
            {
                "fields": ("is_deleted", "created_at", "created_by", "updated_at", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def filter_conditions_preview(self, obj):
        return _filter_conditions_preview(obj)

    filter_conditions_preview.short_description = _("Filter conditions")


# Ensure the User admin has search_fields (for ReconciliationConfig.user autocomplete)
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

@admin.register(User)
class CustomUserAdmin(PlainAdmin):
    # keep the default fieldsets/behavior from UserAdmin but add good search fields
    search_fields = ("username", "email", "first_name", "last_name", "id")
    list_display = ("id", "username", "email", "is_active", "is_staff", "is_superuser")
