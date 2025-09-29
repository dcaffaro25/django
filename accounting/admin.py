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

# --------------------------------
# Base admins (scoped vs. non-scoped)
# --------------------------------
class CompanyScopedAdmin(PerPageSupportMixin, admin.ModelAdmin):
    """Use this ONLY for models that actually have a `company` FK."""
    list_filter = ("company",)
    autocomplete_fields = ("company",)
    list_per_page = 100
    list_max_show_all = 5000
    actions = ["delete_selected"]

class PlainAdmin(PerPageSupportMixin, admin.ModelAdmin):
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
    list_filter = ()
    search_fields = ("code", "name", "symbol")

@admin.register(Bank)
class BankAdmin(PlainAdmin):
    list_display = ("id", "bank_code", "name", "country", "is_active", "created_at")
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
    # You can autocomplete M2M in modern Django, but also keep filter_horizontal for UX:
    autocomplete_fields = ("company", "journal_entries", "bank_transactions")
    filter_horizontal = ("journal_entries", "bank_transactions")
    search_fields = ("reference", "notes", "status")

@admin.register(ReconciliationConfig)
class ReconciliationConfigAdmin(PlainAdmin):
    # Has a 'company' FK and a 'user' FK but is not TenantAware — still fine.
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

# (Optional) auto-register any models not explicitly registered above:
for model in apps.get_app_config("accounting").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
