# accounting/admin.py
from django.contrib import admin
from django.apps import apps
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.utils import model_ngettext
from django.db import transaction as db_transaction

from .models import (
    Currency, CostCenter, Bank, BankAccount, AllocationBase,
    Account, Transaction, JournalEntry, Rule,
    BankTransaction, Reconciliation, ReconciliationTask, ReconciliationConfig
)
from .models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
    FinancialStatement,
    FinancialStatementLine,
    FinancialStatementComparison,
)
from multitenancy.admin import PlainAdmin, CompanyScopedAdmin

# Batch size for bulk operations to avoid memory issues
BULK_DELETE_BATCH_SIZE = 1000



@admin.register(Currency)
class CurrencyAdmin(PlainAdmin):
    list_display = ("id", "code", "name", "symbol", "created_at", "updated_at")
    search_fields = ("code", "name", "symbol")

@admin.register(Bank)
class BankAdmin(PlainAdmin):
    list_display = ("id", "bank_code", "name", "country", "is_active", "notes")
    list_filter = ("is_active", "country", "notes")
    search_fields = ("bank_code", "name", "country", "notes")

@admin.register(BankAccount)
class BankAccountAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "bank", "account_number", "entity", "currency", "branch_id", "company", "notes")
    list_filter = ("bank", "currency", "entity", "company", "notes")
    autocomplete_fields = ("company", "entity", "bank", "currency")
    search_fields = (
        "name", "account_number", "branch_id", "notes",
        "bank__name", "bank__bank_code",
        "entity__name",
        "currency__code",
    )

@admin.register(Account)
class AccountAdmin(CompanyScopedAdmin):
    list_display = ("id", "account_code", "name", "parent", "currency", "bank_account", "is_active", "company", "notes")
    list_filter = ("is_active", "currency", "company", "notes")
    autocomplete_fields = ("company", "parent", "currency", "bank_account")
    search_fields = ("account_code", "name", "description", "key_words", "examples", "parent__name", "notes")

@admin.register(CostCenter)
class CostCenterAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "center_type", "company", "balance_date", "balance", "notes")
    list_filter = ("center_type", "company", "notes")
    autocomplete_fields = ("company",)
    search_fields = ("name", "description", "notes")

@admin.register(AllocationBase)
class AllocationBaseAdmin(CompanyScopedAdmin):
    list_display = ("id", "cost_center", "profit_center", "month", "percentage", "company")
    list_filter = ("month", "company")
    autocomplete_fields = ("company", "cost_center", "profit_center")
    search_fields = ("cost_center__name", "profit_center__name")

def delete_reconciliations_for_journal_entries(journal_entry_ids):
    """
    Efficiently delete all reconciliations that reference the given journal entries.
    Uses bulk operations to handle large datasets efficiently.
    """
    if not journal_entry_ids:
        return 0
    
    # Find reconciliations that reference these journal entries
    reconciliations = Reconciliation.objects.filter(
        journal_entries__id__in=journal_entry_ids
    ).distinct()
    
    reconciliation_ids = list(reconciliations.values_list('id', flat=True))
    
    if not reconciliation_ids:
        return 0
    
    # Clear M2M relationships first (more efficient than letting CASCADE handle it)
    # Delete from the through table
    Reconciliation.journal_entries.through.objects.filter(
        reconciliation_id__in=reconciliation_ids
    ).delete()
    
    Reconciliation.bank_transactions.through.objects.filter(
        reconciliation_id__in=reconciliation_ids
    ).delete()
    
    # Now delete the reconciliation records themselves
    deleted_count = Reconciliation.objects.filter(id__in=reconciliation_ids).delete()[0]
    
    return deleted_count


@admin.register(Transaction)
class TransactionAdmin(CompanyScopedAdmin):
    list_display = ("id", "date", "description", "amount", "entity", "currency", "state", "company", "notes")
    list_filter = ("state", "currency", "entity", "company", "date", "notes")
    autocomplete_fields = ("company", "entity", "currency")
    search_fields = ("description", "entity__name", "notes")
    
    @admin.action(description="Delete selected transactions (with journal entries and reconciliations)")
    def fast_delete_selected(self, request, queryset):
        """
        Optimized bulk delete for transactions that:
        1. Gets all related journal entry IDs first
        2. Deletes reconciliations that reference those journal entries
        3. Deletes transactions (which CASCADE deletes journal entries)
        
        Handles thousands of records efficiently using batch processing.
        """
        transaction_ids = list(queryset.values_list('id', flat=True))
        total_count = len(transaction_ids)
        
        if not total_count:
            self.message_user(request, "No transactions selected.", level='warning')
            return
        
        # Get all journal entry IDs that will be deleted (CASCADE)
        # We need to do this BEFORE deleting transactions
        journal_entry_ids = list(
            JournalEntry.objects.filter(transaction_id__in=transaction_ids)
            .values_list('id', flat=True)
        )
        
        deleted_reconciliations = 0
        deleted_transactions = 0
        deleted_journal_entries = len(journal_entry_ids)
        
        # Use database transaction to ensure atomicity
        with db_transaction.atomic():
            # Step 1: Delete reconciliations that reference these journal entries
            if journal_entry_ids:
                deleted_reconciliations = delete_reconciliations_for_journal_entries(journal_entry_ids)
            
            # Step 2: Delete transactions in batches (CASCADE will delete journal entries)
            # Process in batches to avoid memory issues with very large datasets
            for i in range(0, total_count, BULK_DELETE_BATCH_SIZE):
                batch_ids = transaction_ids[i:i + BULK_DELETE_BATCH_SIZE]
                batch_queryset = Transaction.objects.filter(id__in=batch_ids)
                deleted_transactions += batch_queryset.delete()[0]
        
        # Build success message
        message_parts = [
            f"Successfully deleted {deleted_transactions} {model_ngettext(self.model, deleted_transactions)}"
        ]
        
        if deleted_journal_entries > 0:
            message_parts.append(f"{deleted_journal_entries} related journal entries")
        
        if deleted_reconciliations > 0:
            message_parts.append(f"{deleted_reconciliations} related reconciliations")
        
        self.message_user(
            request,
            ". ".join(message_parts) + ".",
            level='success'
        )
    
    actions = ['fast_delete_selected']

@admin.register(JournalEntry)
class JournalEntryAdmin(CompanyScopedAdmin):
    list_display = ("id", "transaction", "account", "cost_center", "debit_amount", "credit_amount", "state", "date", "company", "notes")
    list_filter = ("state", "date", "company", "notes")
    autocomplete_fields = ("company", "transaction", "account", "cost_center")
    search_fields = (
        "transaction__description",
        "account__name",
        "account__account_code",
        "cost_center__name",
        "notes",
    )
    
    @admin.action(description="Delete selected journal entries (with reconciliations, keep transactions)")
    def fast_delete_selected(self, request, queryset):
        """
        Optimized bulk delete for journal entries that:
        1. Deletes reconciliations that reference these journal entries
        2. Deletes journal entries (transactions are kept)
        
        Handles thousands of records efficiently using batch processing.
        """
        journal_entry_ids = list(queryset.values_list('id', flat=True))
        total_count = len(journal_entry_ids)
        
        if not total_count:
            self.message_user(request, "No journal entries selected.", level='warning')
            return
        
        deleted_reconciliations = 0
        deleted_journal_entries = 0
        
        # Use database transaction to ensure atomicity
        with db_transaction.atomic():
            # Step 1: Delete reconciliations that reference these journal entries
            deleted_reconciliations = delete_reconciliations_for_journal_entries(journal_entry_ids)
            
            # Step 2: Delete journal entries in batches
            # Process in batches to avoid memory issues with very large datasets
            for i in range(0, total_count, BULK_DELETE_BATCH_SIZE):
                batch_ids = journal_entry_ids[i:i + BULK_DELETE_BATCH_SIZE]
                batch_queryset = JournalEntry.objects.filter(id__in=batch_ids)
                deleted_journal_entries += batch_queryset.delete()[0]
        
        # Build success message
        message_parts = [
            f"Successfully deleted {deleted_journal_entries} {model_ngettext(self.model, deleted_journal_entries)}"
        ]
        
        if deleted_reconciliations > 0:
            message_parts.append(f"{deleted_reconciliations} related reconciliations")
        
        message_parts.append("(transactions were preserved)")
        
        self.message_user(
            request,
            ". ".join(message_parts) + ".",
            level='success'
        )
    
    actions = ['fast_delete_selected']

@admin.register(BankTransaction)
class BankTransactionAdmin(CompanyScopedAdmin):
    list_display = ("id", "date", "description", "amount", "bank_account", "currency", "status", "tx_hash", "company", "notes")
    list_filter = ("status", "currency", "bank_account__bank", "company", "date", "notes")
    autocomplete_fields = ("company", "bank_account", "currency")
    search_fields = (
        "description",
        "reference_number",
        "tx_hash",
        "bank_account__name",
        "bank_account__account_number",
        "bank_account__entity__name",
        "currency__code",
        "notes",
    )

@admin.register(Reconciliation)
class ReconciliationAdmin(CompanyScopedAdmin):
    list_display = ("id", "status", "reference", "company", "notes")
    list_filter = ("status", "company", "notes")
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


# Financial Statements Admin

class FinancialStatementLineTemplateInline(admin.TabularInline):
    model = FinancialStatementLineTemplate
    extra = 0
    fields = (
        "line_number", "label", "line_type", "account", "account_code_prefix",
        "calculation_type", "indent_level", "is_bold"
    )
    autocomplete_fields = ("account", "parent_line")
    ordering = ("line_number",)


@admin.register(FinancialStatementTemplate)
class FinancialStatementTemplateAdmin(CompanyScopedAdmin):
    list_display = ("id", "name", "report_type", "is_active", "is_default", "company", "created_at")
    list_filter = ("report_type", "is_active", "is_default", "company")
    autocomplete_fields = ("company",)
    search_fields = ("name", "description", "report_type")
    readonly_fields = ("created_at", "updated_at")
    inlines = [FinancialStatementLineTemplateInline]
    fieldsets = (
        ("Informações Básicas", {
            "fields": ("name", "report_type", "description", "company", "is_active", "is_default")
        }),
        ("Opções de Formatação", {
            "fields": ("show_zero_balances", "show_account_codes", "show_percentages", "group_by_cost_center")
        }),
        ("Metadados", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(FinancialStatementLineTemplate)
class FinancialStatementLineTemplateAdmin(admin.ModelAdmin):
    list_display = ("id", "template", "line_number", "label", "line_type", "calculation_type", "indent_level")
    list_filter = ("line_type", "calculation_type", "template__report_type", "template")
    search_fields = ("label", "template__name", "account_code_prefix")
    autocomplete_fields = ("template", "account", "parent_line")
    ordering = ("template", "line_number")
    list_select_related = ("template", "account")


class FinancialStatementLineInline(admin.TabularInline):
    model = FinancialStatementLine
    extra = 0
    fields = ("line_number", "label", "line_type", "debit_amount", "credit_amount", "balance", "indent_level", "is_bold")
    readonly_fields = ("debit_amount", "credit_amount", "balance")
    ordering = ("line_number",)
    can_delete = False


@admin.register(FinancialStatement)
class FinancialStatementAdmin(CompanyScopedAdmin):
    list_display = (
        "id", "name", "report_type", "start_date", "end_date", "as_of_date",
        "status", "currency", "generated_at", "company"
    )
    list_filter = ("report_type", "status", "currency", "company", "generated_at", "start_date", "end_date")
    autocomplete_fields = ("company", "template", "currency", "generated_by")
    search_fields = ("name", "template__name", "notes")
    readonly_fields = ("generated_at", "total_assets", "total_liabilities", "total_equity", "net_income")
    inlines = [FinancialStatementLineInline]
    date_hierarchy = "end_date"
    fieldsets = (
        ("Informações Básicas", {
            "fields": ("template", "name", "report_type", "company", "status", "currency")
        }),
        ("Período", {
            "fields": ("start_date", "end_date", "as_of_date")
        }),
        ("Totais Calculados", {
            "fields": ("total_assets", "total_liabilities", "total_equity", "net_income"),
            "classes": ("collapse",)
        }),
        ("Metadados", {
            "fields": ("generated_by", "generated_at", "notes"),
            "classes": ("collapse",)
        }),
    )


@admin.register(FinancialStatementLine)
class FinancialStatementLineAdmin(admin.ModelAdmin):
    list_display = ("id", "statement", "line_number", "label", "line_type", "balance", "indent_level")
    list_filter = ("line_type", "statement__report_type", "statement")
    search_fields = ("label", "statement__name")
    autocomplete_fields = ("statement", "line_template")
    ordering = ("statement", "line_number")
    list_select_related = ("statement", "line_template")
    readonly_fields = ("debit_amount", "credit_amount", "balance", "account_ids")


@admin.register(FinancialStatementComparison)
class FinancialStatementComparisonAdmin(CompanyScopedAdmin):
    list_display = (
        "id", "name", "comparison_type", "base_statement", "comparison_statement",
        "created_at", "company"
    )
    list_filter = ("comparison_type", "company", "created_at")
    autocomplete_fields = ("company", "base_statement", "comparison_statement")
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)
    fieldsets = (
        ("Informações Básicas", {
            "fields": ("name", "description", "company", "comparison_type")
        }),
        ("Declarações Comparadas", {
            "fields": ("base_statement", "comparison_statement")
        }),
        ("Metadados", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

# (Optional) auto-register anything missed
for model in apps.get_app_config("accounting").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
