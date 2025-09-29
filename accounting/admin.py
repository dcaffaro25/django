# accounting/admin.py
from django.contrib import admin
from django.apps import apps
from django.contrib.admin.views.main import ChangeList

from .models import (
    Currency, CostCenter, Bank, BankAccount, AllocationBase,
    Account, Transaction, JournalEntry, Rule,
    BankTransaction, Reconciliation, ReconciliationTask, ReconciliationConfig
)

# ----------------------------
# Per-page selector (optional)
# ----------------------------
from django.contrib import admin
from django.apps import apps
from django.contrib.admin.views.main import ChangeList

from .models import (
    Currency, CostCenter, Bank, BankAccount, AllocationBase,
    Account, Transaction, JournalEntry, Rule,
    BankTransaction, Reconciliation, ReconciliationTask, ReconciliationConfig
)

# ----------------------------
# Per-page selector (optional)
# ----------------------------
class VariablePerPageChangeList(ChangeList):
    def get_results(self, request):
        model_label = self.model._meta.label_lower
        session_key = f"admin:{model_label}:per_page"
        raw = request.GET.get("per_page") or request.session.get(session_key)
        try:
            per_page = int(raw)
            per_page = max(10, min(per_page, 1000))
            self.list_per_page = per_page
            request.session[session_key] = per_page
        except (TypeError, ValueError):
            pass
        super().get_results(request)

class PerPageSupportMixin:
    def get_changelist(self, request, **kwargs):
        return VariablePerPageChangeList

# ----------------------------
# Audit columns mixin
# ----------------------------
class AuditColsMixin:
    """
    Adds created/updated audit info to list display and form if the model
    defines these fields (created_at, created_by, updated_at, updated_by).
    Safe for models without them.
    """

    # --- list display helpers (work even if field is missing; just not appended)
    def created_at_col(self, obj):
        return getattr(obj, "created_at", None)
    created_at_col.short_description = "Created at"
    created_at_col.admin_order_field = "created_at"

    def updated_at_col(self, obj):
        return getattr(obj, "updated_at", None)
    updated_at_col.short_description = "Updated at"
    updated_at_col.admin_order_field = "updated_at"

    def created_by_col(self, obj):
        user = getattr(obj, "created_by", None)
        return getattr(user, "username", str(user)) if user else None
    created_by_col.short_description = "Created by"
    created_by_col.admin_order_field = "created_by"

    def updated_by_col(self, obj):
        user = getattr(obj, "updated_by", None)
        return getattr(user, "username", str(user)) if user else None
    updated_by_col.short_description = "Updated by"
    updated_by_col.admin_order_field = "updated_by"

    # Append audit columns dynamically if fields exist
    def get_list_display(self, request):
        base = list(super().get_list_display(request))
        names = {f.name for f in self.model._meta.fields}

        if "created_at" in names:
            base.append("created_at_col")
        if "created_by" in names:
            base.append("created_by_col")
        if "updated_at" in names:
            base.append("updated_at_col")
        if "updated_by" in names:
            base.append("updated_by_col")

        return tuple(base)

    # Add audit fields to list filters if present
    def get_list_filter(self, request):
        base = list(getattr(self, "list_filter", []))
        names = {f.name for f in self.model._meta.fields}
        if "created_at" in names and "created_at" not in base:
            base.append("created_at")
        if "created_by" in names and "created_by" not in base:
            base.append("created_by")
        if "updated_at" in names and "updated_at" not in base:
            base.append("updated_at")
        if "updated_by" in names and "updated_by" not in base:
            base.append("updated_by")
        return base

    # Make audit fields read-only if present
    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        names = {f.name for f in self.model._meta.fields}
        for f in ("created_at", "created_by", "updated_at", "updated_by"):
            if f in names and f not in ro:
                ro.append(f)
        return ro

    # Use created_at for date hierarchy if present
    def get_date_hierarchy(self, request):
        if any(f.name == "created_at" for f in self.model._meta.fields):
            return "created_at"
        # Let parent decide (usually None)
        return getattr(super(), "get_date_hierarchy", lambda r: None)(request)

    # Avoid N+1 on user columns when present
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        names = {f.name for f in self.model._meta.fields}
        to_sr = []
        if "created_by" in names:
            to_sr.append("created_by")
        if "updated_by" in names:
            to_sr.append("updated_by")
        if to_sr:
            qs = qs.select_related(*to_sr)
        return qs

# --------------------------------
# Base admins (scoped vs. non-scoped)
# --------------------------------
class CompanyScopedAdmin(AuditColsMixin, PerPageSupportMixin, admin.ModelAdmin):
    """Use this ONLY for models that actually have a `company` FK."""
    list_filter = ("company",)
    autocomplete_fields = ("company",)
    list_per_page = 100
    list_max_show_all = 5000
    actions = ["delete_selected"]

class PlainAdmin(AuditColsMixin, PerPageSupportMixin, admin.ModelAdmin):
    """For models with no `company` field."""
    list_per_page = 100
    list_max_show_all = 5000
    actions = ["delete_selected"]

# ----------------
# Concrete admins
# ----------------

@admin.register(Currency)
class CurrencyAdmin(PlainAdmin):
    list_display = ("id", "code", "name", "symbol", "created_at", "updated_at")
    search_fields = ("code", "name", "symbol")

@admin.register(Bank)
class BankAdmin(PlainAdmin):
    list_display = ("id", "bank_code", "name", "country", "is_active")
    list_filter = ("is_active", "country")
    search_fields = ("bank_code", "name", "country")

@admin.register(BankAccount)
class BankAccountAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "bank", "account_number", "entity", "currency", "branch_id", "company")
    list_filter = ("bank", "currency", "entity", "company")
    autocomplete_fields = ("company", "entity", "bank", "currency")
    search_fields = (
        "name", "account_number", "branch_id",
        "bank__name", "bank__bank_code",
        "entity__name",
        "currency__code",
    )

@admin.register(Account)
class AccountAdmin(CompanyScopedAdmin):
    list_display = ("id", "account_code", "name", "parent", "currency", "bank_account", "is_active", "company")
    list_filter = ("is_active", "currency", "company")
    autocomplete_fields = ("company", "parent", "currency", "bank_account")
    search_fields = ("account_code", "name", "description", "key_words", "examples", "parent__name")

@admin.register(CostCenter)
class CostCenterAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "center_type", "company", "balance_date", "balance")
    list_filter = ("center_type", "company")
    autocomplete_fields = ("company",)
    search_fields = ("name", "description")

@admin.register(AllocationBase)
class AllocationBaseAdmin(CompanyScopedAdmin):
    list_display = ("id", "cost_center", "profit_center", "month", "percentage", "company")
    list_filter = ("month", "company")
    autocomplete_fields = ("company", "cost_center", "profit_center")
    search_fields = ("cost_center__name", "profit_center__name")

@admin.register(Transaction)
class TransactionAdmin(CompanyScopedAdmin):
    list_display = ("id", "date", "description", "amount", "entity", "currency", "state", "company")
    list_filter = ("state", "currency", "entity", "company", "date")
    autocomplete_fields = ("company", "entity", "currency")
    search_fields = ("description", "entity__name")

@admin.register(JournalEntry)
class JournalEntryAdmin(CompanyScopedAdmin):
    list_display = ("id", "transaction", "account", "cost_center", "debit_amount", "credit_amount", "state", "date", "company")
    list_filter = ("state", "date", "company")
    autocomplete_fields = ("company", "transaction", "account", "cost_center")
    search_fields = (
        "transaction__description",
        "account__name",
        "account__account_code",
        "cost_center__name",
    )

@admin.register(BankTransaction)
class BankTransactionAdmin(CompanyScopedAdmin):
    list_display = ("id", "date", "description", "amount", "bank_account", "currency", "status", "tx_hash", "company")
    list_filter = ("status", "currency", "bank_account__bank", "company", "date")
    autocomplete_fields = ("company", "bank_account", "currency")
    search_fields = (
        "description",
        "reference_number",
        "tx_hash",
        "bank_account__name",
        "bank_account__account_number",
        "bank_account__entity__name",
        "currency__code",
    )

@admin.register(Reconciliation)
class ReconciliationAdmin(CompanyScopedAdmin):
    list_display = ("id", "status", "reference", "company")
    list_filter = ("status", "company")
    autocomplete_fields = ("company", "journal_entries", "bank_transactions")
    filter_horizontal = ("journal_entries", "bank_transactions")
    search_fields = ("reference", "notes", "status")

@admin.register(ReconciliationConfig)
class ReconciliationConfigAdmin(PlainAdmin):
    list_display = ("id", "scope", "name", "company", "user", "is_default", "updated_at")
    list_filter = ("scope", "is_default", "company")
    autocomplete_fields = ("company", "user")
    search_fields = ("name", "description", "company__name", "user__username")

@admin.register(ReconciliationTask)
class ReconciliationTaskAdmin(PlainAdmin):
    list_display = ("id", "task_id", "tenant_id", "status", "created_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("task_id", "tenant_id", "status")

@admin.register(Rule)
class RuleAdmin(PlainAdmin):
    list_display = ("id", "name", "model", "action")
    list_filter = ("model", "action")
    search_fields = ("name", "model", "action", "description")

# (Optional) auto-register anything missed
for model in apps.get_app_config("accounting").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
