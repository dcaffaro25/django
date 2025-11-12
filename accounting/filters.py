# filters.py
from django.db.models import Exists, OuterRef, Q
from django_filters import rest_framework as filters
from accounting.models import BankTransaction, Transaction, JournalEntry, Reconciliation

class NumberInFilter(filters.BaseInFilter, filters.NumberFilter): ...
class CharInFilter(filters.BaseInFilter, filters.CharFilter): ...

class BankTransactionFilter(filters.FilterSet):
    # Ranges
    date_from   = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to     = filters.DateFilter(field_name="date", lookup_expr="lte")
    amount_min  = filters.NumberFilter(field_name="amount", lookup_expr="gte")
    amount_max  = filters.NumberFilter(field_name="amount", lookup_expr="lte")

    # Lists / IN
    id__in      = NumberInFilter(field_name="id", lookup_expr="in")
    status__in  = CharInFilter(field_name="status", lookup_expr="in")

    # Booleans / flags
    unreconciled = filters.BooleanFilter(method="filter_unreconciled")

    # Exact / nested (✅ fixed to go through bank_account)
    entity          = filters.NumberFilter(field_name="bank_account__entity_id")
    entity__in      = NumberInFilter(field_name="bank_account__entity_id", lookup_expr="in")
    entity_name     = filters.CharFilter(field_name="bank_account__entity__name", lookup_expr="icontains")

    bank_account    = filters.NumberFilter(field_name="bank_account_id")
    currency        = filters.NumberFilter(field_name="currency_id")
    tx_hash         = filters.CharFilter(field_name="tx_hash", lookup_expr="exact")

    # Optional niceties
    bank            = filters.NumberFilter(field_name="bank_account__bank_id")
    account_number  = filters.CharFilter(field_name="bank_account__account_number", lookup_expr="icontains")
    account_name    = filters.CharFilter(field_name="bank_account__name", lookup_expr="icontains")

    # Text contains
    description     = filters.CharFilter(field_name="description", lookup_expr="icontains")
    reference_number = filters.CharFilter(field_name="reference_number", lookup_expr="icontains")

    ordering = filters.OrderingFilter(
        fields=(("date","date"),("amount","amount"),("id","id"),("created_at","created_at"))
    )

    class Meta:
        model = BankTransaction
        fields = []  # all handled above

    def filter_unreconciled(self, qs, name, value: bool):
        # Keep your related name; add .distinct() to avoid dup rows when joins are present
        return qs.filter(reconciliations__isnull=True).distinct() if value else qs


class TransactionFilter(filters.FilterSet):
    date_from   = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to     = filters.DateFilter(field_name="date", lookup_expr="lte")
    amount_min  = filters.NumberFilter(field_name="amount", lookup_expr="gte")
    amount_max  = filters.NumberFilter(field_name="amount", lookup_expr="lte")
    state__in   = CharInFilter(field_name="state", lookup_expr="in")

    # If Transaction has a real FK `entity`, using 'entity_id' here still works in Django
    entity      = filters.NumberFilter(field_name="entity_id")
    currency    = filters.NumberFilter(field_name="currency_id")

    description = filters.CharFilter(field_name="description", lookup_expr="icontains")
    
    # Booleans / flags
    unreconciled = filters.BooleanFilter(method="filter_unreconciled")
    
    # ⚠ Only keep this if Transaction actually has this field
    balance_validated = filters.BooleanFilter(field_name="balance_validated")

    ordering = filters.OrderingFilter(
        fields=(("date","date"),("amount","amount"),("id","id"),("created_at","created_at"))
    )

    class Meta:
        model = Transaction
        fields = []
        
    # ---- internal helpers ----
    def _annotate_recon_flags(self, qs):
        # Relevant JEs for this transaction (bank-related)
        relevant_jes = JournalEntry.objects.filter(
            transaction_id=OuterRef('id'),
            account__bank_account__isnull=False,
        )
        # A JE has at least one OK reconciliation
        ok_recon = Reconciliation.objects.filter(
            journal_entry_id=OuterRef('id'),
            status__in=['matched', 'approved'],
        )

        # There exists a relevant JE with NO ok reconciliation
        nonreconciled_exists = Exists(
            relevant_jes.annotate(has_ok=Exists(ok_recon)).filter(has_ok=False)
        )
        # There exists a relevant JE with ok reconciliation
        any_reconciled_exists = Exists(
            relevant_jes.annotate(has_ok=Exists(ok_recon)).filter(has_ok=True)
        )

        return qs.annotate(
            has_rel=Exists(relevant_jes),
            has_nonreconciled=nonreconciled_exists,
            has_any_reconciled=any_reconciled_exists,
        )

    # ---- public filters ----
    def filter_reconciled(self, qs, name, value: bool):
        """
        reconciled=true  -> only fully matched (all relevant JEs reconciled)
        reconciled=false -> pending or mixed
        """
        qs = self._annotate_recon_flags(qs)
        if value:
            return qs.filter(has_rel=True, has_nonreconciled=False).distinct()
        # not fully matched: either no relevant JEs (pending) or mixed/pending
        return qs.filter(Q(has_rel=False) | Q(has_nonreconciled=True)).distinct()

    def filter_unreconciled(self, qs, name, value: bool):
        """
        unreconciled=true  -> there exists at least one relevant JE not reconciled
        unreconciled=false -> no constraint
        """
        if not value:
            return qs
        qs = self._annotate_recon_flags(qs)
        return qs.filter(has_nonreconciled=True).distinct()

    def filter_reconciliation_status(self, qs, name, value: str):
        """
        ?reconciliation_status=matched|pending|mixed
        """
        qs = self._annotate_recon_flags(qs)
        v = (value or "").lower()
        if v == "matched":
            return qs.filter(has_rel=True, has_nonreconciled=False).distinct()
        elif v == "pending":
            # No relevant JEs OR none of the relevant JEs are reconciled
            return qs.filter(Q(has_rel=False) | Q(has_any_reconciled=False)).distinct()
        elif v == "mixed":
            # Has relevant JEs and both reconciled and unreconciled among them
            return qs.filter(has_rel=True, has_any_reconciled=True, has_nonreconciled=True).distinct()
        return qs

class JournalEntryFilter(filters.FilterSet):
    bank_designation_pending = filters.BooleanFilter(field_name="bank_designation_pending")
    has_designated_bank = filters.BooleanFilter(method="filter_has_designated_bank")

    def filter_has_designated_bank(self, qs, name, value):
        if value is True:
            return qs.filter(account__bank_account__isnull=False)
        if value is False:
            return qs.filter(account__bank_account__isnull=True)
        return qs