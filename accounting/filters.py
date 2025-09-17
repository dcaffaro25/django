# filters.py (e.g. api/filters.py)
from django_filters import rest_framework as filters
from accounting.models import BankTransaction, Transaction

# helpers for ?id__in=1,2,3 & ?status__in=pending,review
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

    # Exact/nested
    entity      = filters.NumberFilter(field_name="entity_id")
    bank_account= filters.NumberFilter(field_name="bank_account_id")
    currency    = filters.NumberFilter(field_name="currency_id")
    tx_hash     = filters.CharFilter(field_name="tx_hash", lookup_expr="exact")

    # Text contains (case-insensitive)
    description = filters.CharFilter(field_name="description", lookup_expr="icontains")
    reference_number = filters.CharFilter(field_name="reference_number", lookup_expr="icontains")

    # Allow URL ordering via ?ordering=-date,amount (declared in ViewSet)
    ordering = filters.OrderingFilter(
        fields=(("date","date"),("amount","amount"),("id","id"),("created_at","created_at"))
    )

    class Meta:
        model = BankTransaction
        fields = []  # all handled above

    def filter_unreconciled(self, qs, name, value: bool):
        return qs.filter(reconciliations__isnull=True) if value else qs

class TransactionFilter(filters.FilterSet):
    date_from   = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to     = filters.DateFilter(field_name="date", lookup_expr="lte")
    amount_min  = filters.NumberFilter(field_name="amount", lookup_expr="gte")
    amount_max  = filters.NumberFilter(field_name="amount", lookup_expr="lte")
    state__in   = CharInFilter(field_name="state", lookup_expr="in")

    entity      = filters.NumberFilter(field_name="entity_id")
    currency    = filters.NumberFilter(field_name="currency_id")

    description = filters.CharFilter(field_name="description", lookup_expr="icontains")
    balance_validated = filters.BooleanFilter(field_name="balance_validated")

    ordering = filters.OrderingFilter(
        fields=(("date","date"),("amount","amount"),("id","id"),("created_at","created_at"))
    )

    class Meta:
        model = Transaction
        fields = []
