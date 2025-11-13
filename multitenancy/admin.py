# multitenancy/admin.py
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from .models import Company, Entity  # adjust imports to your actual models
from django.contrib.admin.utils import model_ngettext
from django.contrib.admin.views.main import ChangeList
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.contrib.admin import SimpleListFilter

User = get_user_model()

class FastDeleteMixin:
    """
    Mixin to replace Django's default 'delete_selected' action with a fast
    deletion that avoids building a big confirmation page.  Use with caution:
    there is no per-object confirmation!
    """
    @admin.action(description="Delete selected records")
    def fast_delete_selected(self, request, queryset):
        count = queryset.count()
        if count:
            # Delete in bulk without confirmation; wraps in a single transaction
            queryset.delete()
            self.message_user(
                request,
                f"Successfully deleted {count} {model_ngettext(self.model, count)}.",
            )

    def get_actions(self, request):
        actions = super().get_actions(request)
        # Remove the built-in delete action, if present
        if "delete_selected" in actions:
            del actions["delete_selected"]
        # Add our fast delete action
        actions["fast_delete_selected"] = (
            self.fast_delete_selected,
            "fast_delete_selected",
            "Delete selected records",
        )
        return actions

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
        return [(n, str(n)) for n in (25, 50, 100, 200, 500, 1000)]

    def queryset(self, request, queryset):
        # no filtering happens – this simply exposes ?per_page= in the query string
        return queryset


class CompanyScopedAdmin(FastDeleteMixin, AuditColsMixin, admin.ModelAdmin):
    list_per_page = 100
    list_max_show_all = 5000

    def get_list_per_page(self, request):
        per_page = request.GET.get("per_page")
        if per_page:
            try:
                per_page_int = int(per_page)
                if 10 <= per_page_int <= 1000:
                    request.session[
                        f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
                    ] = per_page_int
                    return per_page_int
            except (ValueError, TypeError):
                pass
        return request.session.get(
            f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page",
            self.list_per_page,
        )

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        filters.append(PerPageFilter)
        return filters

class PlainAdmin(FastDeleteMixin, AuditColsMixin, admin.ModelAdmin):
    list_per_page = 100
    list_max_show_all = 5000

    def get_list_per_page(self, request):
        per_page = request.GET.get("per_page")
        if per_page:
            try:
                per_page_int = int(per_page)
                if 10 <= per_page_int <= 1000:
                    request.session[
                        f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page"
                    ] = per_page_int
                    return per_page_int
            except (ValueError, TypeError):
                pass
        return request.session.get(
            f"admin:{self.opts.app_label}.{self.opts.model_name}:per_page",
            self.list_per_page,
        )

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        filters.append(PerPageFilter)
        return filters

@admin.register(Company)
class CompanyAdmin(PlainAdmin):
    list_display = ("id", "name", "subdomain", "created_at")
    search_fields = ("name", "subdomain", "id")
    list_filter = ("created_at",)
    # if you also use autocomplete to Company somewhere else:
    # date_hierarchy = "created_at"

@admin.register(Entity)
class EntityAdmin(CompanyScopedAdmin):
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
class CustomUserAdmin(PlainAdmin):
    # keep the default fieldsets/behavior from UserAdmin but add good search fields
    search_fields = ("username", "email", "first_name", "last_name", "id")
    list_display = ("id", "username", "email", "is_active", "is_staff", "is_superuser")
