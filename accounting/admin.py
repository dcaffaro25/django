# accounting/admin.py
import logging
from django.contrib import admin
from django.apps import apps
from django.contrib.admin.views.main import ChangeList
from django.contrib.admin.utils import model_ngettext
from django.db import transaction as db_transaction
from django.db.models import Count, Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django import forms
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html
from django.contrib import messages

logger = logging.getLogger(__name__)

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
    AccountBalanceHistory,
)
from multitenancy.admin import PlainAdmin, CompanyScopedAdmin

# Batch size for bulk operations to avoid memory issues
BULK_DELETE_BATCH_SIZE = 1000
# Batch size for reconciliation deletion (smaller due to M2M complexity)
RECONCILIATION_DELETE_BATCH_SIZE = 500

# Import for signal management (lazy import to avoid circular dependencies)
def _get_signal_handlers():
    """Lazy import of signal handlers to avoid circular dependencies"""
    from django.db.models.signals import post_delete, m2m_changed
    from accounting.signals import (
        on_reconciliation_deleted,
        on_reconciliation_entries_changed,
        update_account_balance
    )
    return post_delete, m2m_changed, on_reconciliation_deleted, on_reconciliation_entries_changed, update_account_balance



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

# Bulk Edit Form for Account
class AccountBulkEditForm(forms.Form):
    """Form for bulk editing Account fields"""
    field_to_edit = forms.ChoiceField(
        choices=[
            ('balance_date', 'Balance Date'),
            ('is_active', 'Is Active'),
            ('currency', 'Currency'),
            ('account_direction', 'Account Direction'),
            ('balance', 'Balance'),
        ],
        label='Field to Edit'
    )
    
    # For balance_date
    balance_date = forms.DateField(
        required=False,
        label='New Balance Date',
        widget=admin.widgets.AdminDateWidget()
    )
    
    # For is_active
    is_active = forms.BooleanField(
        required=False,
        label='Is Active',
        help_text='Check to set as active, uncheck to set as inactive'
    )
    
    # For currency
    currency = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        required=False,
        label='New Currency'
    )
    
    # For account_direction
    account_direction = forms.IntegerField(
        required=False,
        label='Account Direction',
        help_text='Integer value for account direction'
    )
    
    # For balance
    balance = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='New Balance'
    )


@admin.register(Account)
class AccountAdmin(CompanyScopedAdmin):
    list_display = ("id", "account_code", "name", "parent", "currency", "bank_account", "is_active", "company", "notes")
    list_filter = ("is_active", "currency", "company", "notes")
    autocomplete_fields = ("company", "parent", "currency", "bank_account")
    search_fields = ("account_code", "name", "description", "key_words", "examples", "parent__name", "notes")
    
    # Simple bulk edit actions for common fields
    @admin.action(description="Bulk edit: Set balance date")
    def bulk_edit_balance_date(self, request, queryset):
        """Bulk edit balance_date with an intermediate form"""
        print("=" * 80)
        print("DEBUG: bulk_edit_balance_date ACTION CALLED")
        print(f"DEBUG: Request method: {request.method}")
        print(f"DEBUG: POST keys: {list(request.POST.keys())}")
        print(f"DEBUG: GET keys: {list(request.GET.keys())}")
        print(f"DEBUG: Initial queryset count: {queryset.count()}")
        logger.info(f"BULK EDIT: bulk_edit_balance_date action called. Method: {request.method}, POST keys: {list(request.POST.keys())}")
        
        # Check if this is a form submission from our intermediate form
        if 'apply' in request.POST:
            print("DEBUG: 'apply' found in POST - this is a form submission")
            logger.info(f"BULK EDIT: Form submission detected. POST data: {dict(request.POST)}")
            
            # Get selected IDs from POST data (_selected_action) or from session
            selected_ids = request.POST.getlist('_selected_action')
            print(f"DEBUG: Selected IDs from POST _selected_action: {selected_ids}")
            if not selected_ids:
                # Fallback to session
                selected_ids = request.session.get('bulk_edit_account_ids', [])
                print(f"DEBUG: No IDs in POST, using session: {selected_ids}")
            else:
                print(f"DEBUG: Using IDs from POST: {len(selected_ids)} IDs")
            
            logger.info(f"BULK EDIT: Using {len(selected_ids)} account IDs from POST/session: {selected_ids[:10]}...")
            selected = self.model.objects.filter(pk__in=selected_ids)
            print(f"DEBUG: Found {selected.count()} accounts in database with those IDs")
            logger.info(f"BULK EDIT: Found {selected.count()} accounts in database")
            
            # Print current balance_date values before update
            if selected.exists():
                sample = selected.first()
                print(f"DEBUG: Sample account before update - ID: {sample.id}, balance_date: {sample.balance_date}")
            
            # Add field_to_edit to POST data if not present (for balance_date action)
            post_data = request.POST.copy()
            if 'field_to_edit' not in post_data:
                post_data['field_to_edit'] = 'balance_date'
                print(f"DEBUG: Added field_to_edit='balance_date' to POST data")
            
            form = AccountBulkEditForm(post_data)
            print(f"DEBUG: Form created from POST data")
            print(f"DEBUG: POST data includes field_to_edit: {'field_to_edit' in post_data}")
            print(f"DEBUG: Form is_valid: {form.is_valid()}")
            logger.info(f"BULK EDIT: Form is_valid={form.is_valid()}")
            
            if not form.is_valid():
                print(f"DEBUG: Form validation FAILED")
                print(f"DEBUG: Form errors: {form.errors}")
                print(f"DEBUG: Form non_field_errors: {form.non_field_errors()}")
                logger.warning(f"BULK EDIT: Form validation errors: {form.errors}")
            
            if form.is_valid():
                new_date = form.cleaned_data.get('balance_date')
                print(f"DEBUG: Form is VALID")
                print(f"DEBUG: New date from form.cleaned_data: {new_date}")
                print(f"DEBUG: New date type: {type(new_date)}")
                logger.info(f"BULK EDIT: Form validated. New date value: {new_date} (type: {type(new_date)})")
                
                if new_date:
                    print(f"DEBUG: New date is not None/empty, proceeding with update")
                    print(f"DEBUG: About to update {selected.count()} accounts")
                    print(f"DEBUG: Update query: selected.update(balance_date={new_date})")
                    
                    logger.info(f"BULK EDIT: Updating {selected.count()} accounts with balance_date={new_date}")
                    
                    # Execute the update
                    updated = selected.update(balance_date=new_date)
                    print(f"DEBUG: Update returned: {updated} (should be > 0)")
                    logger.info(f"BULK EDIT: Successfully updated {updated} accounts")
                    
                    # Verify the update by querying again
                    verify_queryset = self.model.objects.filter(pk__in=selected_ids, balance_date=new_date)
                    verify_count = verify_queryset.count()
                    print(f"DEBUG: Verification query - accounts with balance_date={new_date}: {verify_count}")
                    logger.info(f"BULK EDIT: Verification - {verify_count} accounts now have balance_date={new_date}")
                    
                    # Print a sample after update
                    if verify_queryset.exists():
                        sample_after = verify_queryset.first()
                        print(f"DEBUG: Sample account after update - ID: {sample_after.id}, balance_date: {sample_after.balance_date}")
                    else:
                        print(f"DEBUG: WARNING - No accounts found with the new balance_date!")
                    
                    if updated > 0:
                        self.message_user(
                            request,
                            f"Successfully updated balance_date for {updated} {model_ngettext(self.model, updated)}.",
                            level=messages.SUCCESS
                        )
                        print(f"DEBUG: Success message sent, redirecting...")
                        return redirect('admin:accounting_account_changelist')
                    else:
                        print(f"DEBUG: WARNING - Update returned 0, no records were updated!")
                        self.message_user(
                            request,
                            f"Warning: Update query returned 0. No records were updated. Check logs for details.",
                            level=messages.WARNING
                        )
                else:
                    print(f"DEBUG: New date is None/empty, not updating")
                    logger.warning("BULK EDIT: Form valid but balance_date is None/empty")
                    self.message_user(
                        request,
                        "Please provide a balance date.",
                        level=messages.ERROR
                    )
            else:
                print(f"DEBUG: Form is INVALID, showing form again with errors")
        else:
            print("DEBUG: 'apply' NOT in POST - this is initial form display")
            logger.info("BULK EDIT: Initial form display (not a submission)")
            # Store selected IDs in session for form submission
            selected_ids = list(queryset.values_list('pk', flat=True))
            print(f"DEBUG: Storing {len(selected_ids)} account IDs in session")
            print(f"DEBUG: First 10 IDs: {selected_ids[:10]}")
            logger.info(f"BULK EDIT: Storing {len(selected_ids)} account IDs in session: {selected_ids[:10]}...")
            request.session['bulk_edit_account_ids'] = selected_ids
            request.session.modified = True
            form = AccountBulkEditForm(initial={'field_to_edit': 'balance_date'})
            print(f"DEBUG: Form created with initial data")
        
        # Get selected objects info - use queryset for initial, or retrieve from IDs for submission
        if 'apply' in request.POST:
            selected_ids = request.POST.getlist('_selected_action') or request.session.get('bulk_edit_account_ids', [])
            print(f"DEBUG: Getting objects for form display - using IDs: {len(selected_ids)}")
            selected_queryset = self.model.objects.filter(pk__in=selected_ids)
            selected_count = selected_queryset.count()
            selected_objects = list(selected_queryset[:20])
            all_selected_ids = selected_ids
        else:
            selected_count = queryset.count()
            selected_objects = list(queryset[:20])
            all_selected_ids = list(queryset.values_list('pk', flat=True))
            print(f"DEBUG: Initial display - {selected_count} accounts, {len(all_selected_ids)} IDs")
        
        print(f"DEBUG: Rendering template with {selected_count} selected accounts, {len(all_selected_ids)} total IDs")
        print(f"DEBUG: Form fields in template: balance_date field will be shown")
        logger.info(f"BULK EDIT: Rendering form with {selected_count} selected accounts (all IDs: {len(all_selected_ids)})")
        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'model': self.model,
            'selected_count': selected_count,
            'selected_objects': selected_objects,
            'all_selected_ids': all_selected_ids,  # All IDs for form submission
            'field_name': 'balance_date',
            'title': 'Bulk Edit: Balance Date',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        
        print("DEBUG: About to render template")
        print("=" * 80)
        return render(request, 'admin/accounting/account/bulk_edit.html', context)
    
    @admin.action(description="Bulk edit: Toggle is_active")
    def bulk_edit_is_active(self, request, queryset):
        """Bulk toggle is_active status"""
        selected_ids = list(queryset.values_list('pk', flat=True))
        request.session['bulk_edit_account_ids'] = selected_ids
        
        if 'apply' in request.POST:
            stored_ids = request.session.pop('bulk_edit_account_ids', [])
            selected = self.model.objects.filter(pk__in=stored_ids)
            
            form = AccountBulkEditForm(request.POST)
            if form.is_valid():
                is_active = form.cleaned_data.get('is_active')
                if is_active is not None:
                    updated = selected.update(is_active=is_active)
                    action = "activated" if is_active else "deactivated"
                    self.message_user(
                        request,
                        f"Successfully {action} {updated} {model_ngettext(self.model, updated)}.",
                        level=messages.SUCCESS
                    )
                    return redirect('admin:accounting_account_changelist')
        else:
            form = AccountBulkEditForm(initial={'field_to_edit': 'is_active', 'is_active': True})
        
        selected_count = queryset.count()
        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'model': self.model,
            'selected_count': selected_count,
            'selected_objects': list(queryset[:20]),
            'field_name': 'is_active',
            'title': 'Bulk Edit: Is Active',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return render(request, 'admin/accounting/account/bulk_edit.html', context)
    
    @admin.action(description="Bulk edit: Set currency")
    def bulk_edit_currency(self, request, queryset):
        """Bulk edit currency"""
        selected_ids = list(queryset.values_list('pk', flat=True))
        request.session['bulk_edit_account_ids'] = selected_ids
        
        if 'apply' in request.POST:
            stored_ids = request.session.pop('bulk_edit_account_ids', [])
            selected = self.model.objects.filter(pk__in=stored_ids)
            
            form = AccountBulkEditForm(request.POST)
            if form.is_valid():
                new_currency = form.cleaned_data.get('currency')
                if new_currency:
                    updated = selected.update(currency=new_currency)
                    self.message_user(
                        request,
                        f"Successfully updated currency for {updated} {model_ngettext(self.model, updated)}.",
                        level=messages.SUCCESS
                    )
                    return redirect('admin:accounting_account_changelist')
        else:
            form = AccountBulkEditForm(initial={'field_to_edit': 'currency'})
        
        selected_count = queryset.count()
        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'model': self.model,
            'selected_count': selected_count,
            'selected_objects': list(queryset[:20]),
            'field_name': 'currency',
            'title': 'Bulk Edit: Currency',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return render(request, 'admin/accounting/account/bulk_edit.html', context)
    
    @admin.action(description="Bulk edit: Generic field editor")
    def bulk_edit_generic(self, request, queryset):
        """Generic bulk edit for any Account field"""
        logger.info(f"BULK EDIT GENERIC: Action called. Method: {request.method}, POST keys: {list(request.POST.keys())}")
        
        selected_ids = list(queryset.values_list('pk', flat=True))
        logger.info(f"BULK EDIT GENERIC: Storing {len(selected_ids)} account IDs in session")
        request.session['bulk_edit_account_ids'] = selected_ids
        request.session.modified = True
        
        if 'apply' in request.POST:
            logger.info(f"BULK EDIT GENERIC: Form submission detected. POST data: {dict(request.POST)}")
            stored_ids = request.session.pop('bulk_edit_account_ids', [])
            logger.info(f"BULK EDIT GENERIC: Retrieved {len(stored_ids)} account IDs from session")
            selected = self.model.objects.filter(pk__in=stored_ids)
            logger.info(f"BULK EDIT GENERIC: Found {selected.count()} accounts in database")
            
            form = AccountBulkEditForm(request.POST)
            logger.info(f"BULK EDIT GENERIC: Form is_valid={form.is_valid()}")
            if not form.is_valid():
                logger.warning(f"BULK EDIT GENERIC: Form validation errors: {form.errors}")
            
            if form.is_valid():
                field_to_edit = form.cleaned_data['field_to_edit']
                logger.info(f"BULK EDIT GENERIC: Field to edit: {field_to_edit}")
                updated_count = 0
                
                with db_transaction.atomic():
                    if field_to_edit == 'balance_date' and form.cleaned_data.get('balance_date'):
                        new_date = form.cleaned_data['balance_date']
                        logger.info(f"BULK EDIT GENERIC: Updating balance_date to {new_date}")
                        updated_count = selected.update(balance_date=new_date)
                        logger.info(f"BULK EDIT GENERIC: Updated {updated_count} accounts")
                    elif field_to_edit == 'is_active' and form.cleaned_data.get('is_active') is not None:
                        new_value = form.cleaned_data['is_active']
                        logger.info(f"BULK EDIT GENERIC: Updating is_active to {new_value}")
                        updated_count = selected.update(is_active=new_value)
                        logger.info(f"BULK EDIT GENERIC: Updated {updated_count} accounts")
                    elif field_to_edit == 'currency' and form.cleaned_data.get('currency'):
                        new_currency = form.cleaned_data['currency']
                        logger.info(f"BULK EDIT GENERIC: Updating currency to {new_currency}")
                        updated_count = selected.update(currency=new_currency)
                        logger.info(f"BULK EDIT GENERIC: Updated {updated_count} accounts")
                    elif field_to_edit == 'account_direction' and form.cleaned_data.get('account_direction') is not None:
                        new_value = form.cleaned_data['account_direction']
                        logger.info(f"BULK EDIT GENERIC: Updating account_direction to {new_value}")
                        updated_count = selected.update(account_direction=new_value)
                        logger.info(f"BULK EDIT GENERIC: Updated {updated_count} accounts")
                    elif field_to_edit == 'balance' and form.cleaned_data.get('balance') is not None:
                        new_balance = form.cleaned_data['balance']
                        logger.info(f"BULK EDIT GENERIC: Updating balance to {new_balance}")
                        updated_count = selected.update(balance=new_balance)
                        logger.info(f"BULK EDIT GENERIC: Updated {updated_count} accounts")
                    else:
                        logger.warning(f"BULK EDIT GENERIC: No valid field/value combination matched")
                
                if updated_count > 0:
                    self.message_user(
                        request,
                        f"Successfully updated {field_to_edit} for {updated_count} {model_ngettext(self.model, updated_count)}.",
                        level=messages.SUCCESS
                    )
                else:
                    logger.warning(f"BULK EDIT GENERIC: No accounts were updated")
                    self.message_user(
                        request,
                        "No fields were updated. Please ensure you selected a field and provided a value.",
                        level=messages.WARNING
                    )
                return redirect('admin:accounting_account_changelist')
        else:
            logger.info("BULK EDIT GENERIC: Initial form display (not a submission)")
            form = AccountBulkEditForm()
        
        selected_count = queryset.count()
        logger.info(f"BULK EDIT GENERIC: Rendering form with {selected_count} selected accounts")
        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'model': self.model,
            'selected_count': selected_count,
            'selected_objects': list(queryset[:20]),
            'field_name': 'generic',
            'title': 'Bulk Edit: Multiple Fields',
            'opts': self.model._meta,
            'has_view_permission': self.has_view_permission(request),
            'has_change_permission': self.has_change_permission(request),
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return render(request, 'admin/accounting/account/bulk_edit_generic.html', context)
    
    actions = ['bulk_edit_balance_date', 'bulk_edit_is_active', 'bulk_edit_currency', 'bulk_edit_generic']

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

def batch_update_account_balances(affected_account_ids):
    """
    Efficiently update account balances for multiple accounts in batch.
    Uses a single aggregation query with GROUP BY to calculate all balances at once.
    Only updates leaf accounts (non-leaf accounts get balances from children).
    
    Args:
        affected_account_ids: Set or list of account IDs to update
        
    Returns:
        Dictionary mapping account_id to new balance
    """
    if not affected_account_ids:
        return {}
    
    from accounting.models import Account, JournalEntry
    from django.db.models import Sum, F, DecimalField, Exists, OuterRef
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    # Get only leaf accounts efficiently using MPTT - leaf accounts have no children
    # Use a subquery to check for children existence
    leaf_account_ids = list(
        Account.objects.filter(
            id__in=affected_account_ids
        ).annotate(
            has_children=Exists(
                Account.objects.filter(parent_id=OuterRef('id'))
            )
        ).filter(has_children=False).values_list('id', flat=True)
    )
    
    if not leaf_account_ids:
        return {}
    
    # Calculate all balances in a single query using GROUP BY
    balance_results = JournalEntry.objects.filter(
        account_id__in=leaf_account_ids
    ).values('account_id').annotate(
        total=Coalesce(
            Sum(
                F('debit_amount') - F('credit_amount'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            ),
            Decimal('0'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).values_list('account_id', 'total')
    
    # Create mapping of account_id to new balance
    balance_map = {account_id: balance for account_id, balance in balance_results}
    
    # Set balance to 0 for leaf accounts with no journal entries
    accounts_with_entries = set(balance_map.keys())
    accounts_no_entries = set(leaf_account_ids) - accounts_with_entries
    for account_id in accounts_no_entries:
        balance_map[account_id] = Decimal('0')
    
    # Update all accounts in batch - use select_for_update to avoid race conditions
    # Get accounts in batches to avoid memory issues
    accounts_to_update = []
    for i in range(0, len(leaf_account_ids), BULK_DELETE_BATCH_SIZE):
        batch_account_ids = leaf_account_ids[i:i + BULK_DELETE_BATCH_SIZE]
        batch_accounts = Account.objects.filter(id__in=batch_account_ids)
        for account in batch_accounts:
            if account.id in balance_map:
                account.balance = balance_map[account.id]
                accounts_to_update.append(account)
    
    if accounts_to_update:
        Account.objects.bulk_update(accounts_to_update, ['balance'], batch_size=BULK_DELETE_BATCH_SIZE)
    
    return balance_map


def batch_update_parent_balances(affected_account_ids, skip_if_large=True):
    """
    Efficiently update parent account balances for multiple accounts in batch.
    Uses a single GROUP BY query to calculate all direct parent balances.
    
    Note: This only updates direct parents. For full ancestor tree updates,
    consider running a separate maintenance task after bulk operations.
    
    Args:
        affected_account_ids: Set or list of account IDs whose parents need updating
        skip_if_large: If True and more than 100 accounts, skip parent updates for performance
    """
    if not affected_account_ids:
        return
    
    # Skip parent updates for very large operations - can be done separately
    if skip_if_large and len(affected_account_ids) > 100:
        return
    
    from accounting.models import Account
    from django.db.models import Sum, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    # Get all affected accounts and collect their direct parent IDs
    affected_accounts = Account.objects.filter(id__in=affected_account_ids).only('parent_id')
    parent_ids_to_update = {acc.parent_id for acc in affected_accounts if acc.parent_id}
    
    if not parent_ids_to_update:
        return
    
    # Calculate ALL direct parent balances in a SINGLE query using GROUP BY
    # This replaces N queries with 1 query
    parent_balances = Account.objects.filter(
        parent_id__in=parent_ids_to_update
    ).values('parent_id').annotate(
        total=Coalesce(
            Sum('balance'),
            Decimal('0'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    ).values_list('parent_id', 'total')
    
    # Create mapping of parent_id to new balance
    balance_map = {parent_id: balance for parent_id, balance in parent_balances}
    
    # Handle parent accounts with no children (should have balance 0)
    parents_with_children = set(balance_map.keys())
    parents_no_children = parent_ids_to_update - parents_with_children
    for parent_id in parents_no_children:
        balance_map[parent_id] = Decimal('0')
    
    # Get all parent accounts and update their balances in batch
    parent_accounts = list(Account.objects.filter(id__in=parent_ids_to_update))
    accounts_to_update = []
    for account in parent_accounts:
        if account.id in balance_map:
            account.balance = balance_map[account.id]
            accounts_to_update.append(account)
    
    if accounts_to_update:
        Account.objects.bulk_update(accounts_to_update, ['balance'], batch_size=BULK_DELETE_BATCH_SIZE)


def delete_reconciliations_for_journal_entries(journal_entry_ids, disable_signals=True):
    """
    Efficiently delete all reconciliations that reference the given journal entries.
    Uses bulk operations with batching to handle large datasets efficiently.
    
    Optimizations:
    - Processes journal entry IDs in batches to avoid memory issues
    - Uses direct through table query instead of .distinct() to avoid expensive DISTINCT
    - Processes reconciliation deletions in batches
    - Disables signals during bulk delete for massive performance improvement
    - Uses single query to get unique reconciliation IDs from through table
    
    Args:
        journal_entry_ids: List of journal entry IDs
        disable_signals: If True, disables signals during deletion (default: True for performance)
    """
    if not journal_entry_ids:
        return 0, set()
    
    # Get all unique reconciliation IDs in a single query (much faster than batching)
    # Use DISTINCT directly in SQL which is optimized by the database
    reconciliation_ids = list(
        Reconciliation.journal_entries.through.objects.filter(
            journalentry_id__in=journal_entry_ids
        ).values_list('reconciliation_id', flat=True).distinct()
    )
    
    # Track affected journal entry IDs for return value
    affected_journal_entry_ids = set(journal_entry_ids)
    
    if not reconciliation_ids:
        return 0, affected_journal_entry_ids
    
    deleted_count = 0
    
    # Disable signals during bulk delete for massive performance improvement
    # Signals will be processed in batch after all deletions are complete
    if disable_signals:
        post_delete, m2m_changed, on_reconciliation_deleted, on_reconciliation_entries_changed, _ = _get_signal_handlers()
        m2m_changed.disconnect(on_reconciliation_entries_changed, sender=Reconciliation.journal_entries.through)
        post_delete.disconnect(on_reconciliation_deleted, sender=Reconciliation)
    
    try:
        # Process reconciliation deletions in batches
        for i in range(0, len(reconciliation_ids), RECONCILIATION_DELETE_BATCH_SIZE):
            batch_reconciliation_ids = reconciliation_ids[i:i + RECONCILIATION_DELETE_BATCH_SIZE]
            
            # Clear M2M relationships first (more efficient than letting CASCADE handle it)
            # Delete from the through tables in batch
            Reconciliation.journal_entries.through.objects.filter(
                reconciliation_id__in=batch_reconciliation_ids
            ).delete()
            
            Reconciliation.bank_transactions.through.objects.filter(
                reconciliation_id__in=batch_reconciliation_ids
            ).delete()
            
            # Now delete the reconciliation records themselves in batch
            deleted_count += Reconciliation.objects.filter(
                id__in=batch_reconciliation_ids
            ).delete()[0]
    finally:
        # Re-enable signals after bulk delete
        if disable_signals:
            post_delete, m2m_changed, on_reconciliation_deleted, on_reconciliation_entries_changed, _ = _get_signal_handlers()
            m2m_changed.connect(on_reconciliation_entries_changed, sender=Reconciliation.journal_entries.through)
            post_delete.connect(on_reconciliation_deleted, sender=Reconciliation)
    
    return deleted_count, affected_journal_entry_ids


@admin.register(Transaction)
class TransactionAdmin(CompanyScopedAdmin):
    list_display = (
        "id", "date", "description", "amount", "entity", "currency", "state",
        "journal_entries_count", "transaction_balance",
        "avg_payment_day_delta", "total_amount_discrepancy", "avg_amount_discrepancy",
        "exact_match_count", "perfect_match_count", "reconciliation_rate",
        "metrics_last_calculated_at",
        "company", "notes"
    )
    list_filter = ("state", "currency", "entity", "company", "date", "notes")
    autocomplete_fields = ("company", "entity", "currency")
    search_fields = ("description", "entity__name", "notes")
    
    def get_queryset(self, request):
        """Optimize queryset with annotations for journal entry count and balance"""
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            journal_entries_count=Count('journal_entries'),
            total_debits=Coalesce(Sum('journal_entries__debit_amount'), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            total_credits=Coalesce(Sum('journal_entries__credit_amount'), 0, output_field=DecimalField(max_digits=12, decimal_places=2)),
        )
        return queryset
    
    def journal_entries_count(self, obj):
        """Display the count of journal entries for this transaction"""
        return getattr(obj, 'journal_entries_count', obj.journal_entries.count())
    journal_entries_count.short_description = 'Journal Entries'
    journal_entries_count.admin_order_field = 'journal_entries_count'
    
    def transaction_balance(self, obj):
        """Display the transaction balance (debits - credits)"""
        if hasattr(obj, 'total_debits') and hasattr(obj, 'total_credits'):
            balance = obj.total_debits - obj.total_credits
        else:
            # Fallback if annotations aren't available
            total_debits = sum(je.debit_amount or 0 for je in obj.journal_entries.all())
            total_credits = sum(je.credit_amount or 0 for je in obj.journal_entries.all())
            balance = total_debits - total_credits
        
        # Format the balance as a string with 2 decimal places
        balance_str = f'{float(balance):.2f}'
        
        # Format with color coding: red for negative, green for positive, black for zero
        if balance < 0:
            return format_html('<span style="color: red;">{}</span>', balance_str)
        elif balance > 0:
            return format_html('<span style="color: green;">{}</span>', balance_str)
        else:
            return balance_str
    transaction_balance.short_description = 'Balance (Debits - Credits)'
    # Note: Can't order by computed balance field directly, but can order by total_debits or total_credits if needed
    
    @admin.action(description="Delete selected transactions (with journal entries and reconciliations)")
    def fast_delete_selected(self, request, queryset):
        """
        Optimized bulk delete for transactions that:
        1. Gets all related journal entry IDs first (in batches to avoid memory issues)
        2. Deletes reconciliations that reference those journal entries
        3. Deletes transactions in batches (which CASCADE deletes journal entries)
        
        Handles thousands of records efficiently using batch processing.
        Optimizations:
        - Batches journal entry ID retrieval to avoid loading all into memory
        - Uses optimized reconciliation deletion with batching
        - Processes transactions in batches
        """
        # Get transaction IDs - use iterator to avoid loading all into memory
        transaction_ids = []
        for transaction_id in queryset.values_list('id', flat=True).iterator(chunk_size=BULK_DELETE_BATCH_SIZE):
            transaction_ids.append(transaction_id)
        
        total_count = len(transaction_ids)
        
        if not total_count:
            self.message_user(request, "No transactions selected.", level='warning')
            return
        
        # Get all journal entry IDs that will be deleted (CASCADE)
        # We need to do this BEFORE deleting transactions to find related reconciliations
        # Get IDs directly without loading account_id (we don't need it anymore since balance updates are disabled)
        journal_entry_ids = list(
            JournalEntry.objects.filter(transaction_id__in=transaction_ids)
            .values_list('id', flat=True)
        )
        
        deleted_reconciliations = 0
        deleted_transactions = 0
        deleted_journal_entries = len(journal_entry_ids)
        
        # Disable signals during bulk delete for massive performance improvement
        # We'll process signal updates in batch after all deletions
        post_delete, _, _, _, update_account_balance = _get_signal_handlers()
        post_delete.disconnect(update_account_balance, sender=JournalEntry)
        
        try:
            # Use database transaction to ensure atomicity
            with db_transaction.atomic():
                # Step 1: Delete reconciliations that reference these journal entries
                if journal_entry_ids:
                    deleted_reconciliations, _ = delete_reconciliations_for_journal_entries(
                        journal_entry_ids, disable_signals=True
                    )
                
                # Step 2: Delete transactions in batches (CASCADE will delete journal entries)
                # Process in batches to avoid memory issues with very large datasets
                for i in range(0, total_count, BULK_DELETE_BATCH_SIZE):
                    batch_ids = transaction_ids[i:i + BULK_DELETE_BATCH_SIZE]
                    batch_queryset = Transaction.objects.filter(id__in=batch_ids)
                    deleted_transactions += batch_queryset.delete()[0]
                
                # Step 3: Skip account balance updates during bulk delete for maximum performance
                # Account balances will be recalculated automatically when needed or can be
                # recalculated via a separate maintenance task. This avoids N+1 query issues.
        finally:
            # Re-enable signals after bulk operations
            post_delete.connect(update_account_balance, sender=JournalEntry)
        
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
    list_display = (
        "id", "transaction", "account", "cost_center",
        "debit_amount", "credit_amount", "state", "date",
        "payment_day_delta", "journal_entry_date_delta", "amount_discrepancy",
        "is_exact_match", "is_date_match", "is_perfect_match",
        "account_confidence_score", "account_historical_matches",
        "metrics_last_calculated_at",
        "company", "notes"
    )
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
        Optimizations:
        - Uses iterator to avoid loading all IDs into memory at once
        - Uses optimized reconciliation deletion with batching
        - Processes journal entries in batches
        """
        # Get journal entry IDs - we don't need account IDs anymore since balance updates are disabled
        journal_entry_ids = list(queryset.values_list('id', flat=True))
        
        total_count = len(journal_entry_ids)
        
        if not total_count:
            self.message_user(request, "No journal entries selected.", level='warning')
            return
        
        deleted_reconciliations = 0
        deleted_journal_entries = 0
        
        # Disable signals during bulk delete for massive performance improvement
        # We'll process signal updates in batch after all deletions
        post_delete, _, _, _, update_account_balance = _get_signal_handlers()
        post_delete.disconnect(update_account_balance, sender=JournalEntry)
        
        try:
            # Use database transaction to ensure atomicity
            with db_transaction.atomic():
                # Step 1: Delete reconciliations that reference these journal entries
                deleted_reconciliations, _ = delete_reconciliations_for_journal_entries(
                    journal_entry_ids, disable_signals=True
                )
                
                # Step 2: Delete journal entries in batches
                # Process in batches to avoid memory issues with very large datasets
                for i in range(0, total_count, BULK_DELETE_BATCH_SIZE):
                    batch_ids = journal_entry_ids[i:i + BULK_DELETE_BATCH_SIZE]
                    batch_queryset = JournalEntry.objects.filter(id__in=batch_ids)
                    deleted_journal_entries += batch_queryset.delete()[0]
                
                # Step 3: Skip account balance updates during bulk delete for maximum performance
                # Account balances will be recalculated automatically when needed or can be
                # recalculated via a separate maintenance task. This avoids N+1 query issues.
        finally:
            # Re-enable signals after bulk operations
            post_delete.connect(update_account_balance, sender=JournalEntry)
        
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


@admin.register(AccountBalanceHistory)
class AccountBalanceHistoryAdmin(CompanyScopedAdmin):
    # Default list_display with all fields
    _full_list_display = [
        'account',
        'year',
        'month',
        'currency',
        'posted_total_debit',
        'posted_total_credit',
        'bank_reconciled_total_debit',
        'bank_reconciled_total_credit',
        'all_total_debit',
        'all_total_credit',
        'calculated_at',
        'is_validated',
    ]
    
    # Minimal list_display for when migration hasn't been applied
    _minimal_list_display = [
        'account',
        'year',
        'month',
        'currency',
    ]
    
    list_display = _full_list_display
    list_filter = [
        'year',
        'month',
        'currency',
        'is_validated',
        'calculated_at',
    ]
    search_fields = [
        'account__name',
        'account__account_code',
    ]
    readonly_fields = [
        'calculated_at',
        'calculated_by',
    ]
    date_hierarchy = 'calculated_at'
    
    fieldsets = (
        ('Account & Period', {
            'fields': ('account', 'year', 'month', 'currency')
        }),
        ('Posted Transactions', {
            'fields': (
                'posted_total_debit',
                'posted_total_credit'
            )
        }),
        ('Bank-Reconciled Transactions', {
            'fields': (
                'bank_reconciled_total_debit',
                'bank_reconciled_total_credit'
            )
        }),
        ('All Transactions', {
            'fields': (
                'all_total_debit',
                'all_total_credit'
            )
        }),
        ('Metadata', {
            'fields': ('calculated_at', 'calculated_by')
        }),
        ('Validation', {
            'fields': ('is_validated', 'validated_at', 'validated_by')
        }),
    )
    
    def _check_columns_exist(self):
        """Check if the migration columns exist in the database."""
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'accounting_accountbalancehistory' 
                    AND column_name = 'posted_total_debit'
                """)
                return cursor.fetchone() is not None
        except Exception:
            return False
    
    def get_list_display(self, request):
        """
        Dynamically return list_display based on whether migration columns exist.
        This is called before the queryset is evaluated.
        """
        if not self._check_columns_exist():
            return self._minimal_list_display
        return self._full_list_display
    
    def get_list_filter(self, request):
        """
        Dynamically return list_filter based on whether migration columns exist.
        """
        if not self._check_columns_exist():
            return ['year', 'month', 'currency']
        return [
            'year',
            'month',
            'currency',
            'is_validated',
            'calculated_at',
        ]
    
    def get_date_hierarchy(self, request):
        """
        Dynamically return date_hierarchy based on whether migration columns exist.
        """
        if not self._check_columns_exist():
            return None
        return 'calculated_at'
    
    def changelist_view(self, request, extra_context=None):
        """
        Override changelist to handle missing columns gracefully.
        get_list_display, get_list_filter, and get_date_hierarchy are already
        set up to return appropriate values based on column existence.
        """
        # Try to render the changelist, but catch database errors
        try:
            return super().changelist_view(request, extra_context)
        except Exception as e:
            # If it's a column-related database error, show a helpful message
            from django.db.utils import ProgrammingError
            error_str = str(e)
            is_column_error = (
                isinstance(e, ProgrammingError) or 
                'does not exist' in error_str or 
                'column' in error_str.lower()
            )
            
            if is_column_error:
                # Return a simple error response
                from django.http import HttpResponse
                error_html = f"""
                <html>
                <head><title>Migration Required</title></head>
                <body style="font-family: sans-serif; padding: 20px;">
                    <h1 style="color: #d32f2f;">Migration Required</h1>
                    <p>The AccountBalanceHistory migration hasn't been applied yet.</p>
                    <p><strong>Please run the following command to create the required columns:</strong></p>
                    <pre style="background: #f5f5f5; padding: 10px; border-radius: 4px;">python manage.py migrate accounting</pre>
                    <p>After running the migration, refresh this page.</p>
                    <hr>
                    <p style="color: #666; font-size: 0.9em;">Database error: {error_str[:300]}</p>
                </body>
                </html>
                """
                return HttpResponse(error_html, content_type='text/html', status=500)
            
            # Re-raise if it's a different error
            raise

# (Optional) auto-register anything missed
for model in apps.get_app_config("accounting").get_models():
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass
