# filters.py
from django_filters import rest_framework as filters
from accounting.models import BankTransaction, Transaction

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

    # ⚠ Only keep this if Transaction actually has this field
    balance_validated = filters.BooleanFilter(field_name="balance_validated")

    ordering = filters.OrderingFilter(
        fields=(("date","date"),("amount","amount"),("id","id"),("created_at","created_at"))
    )

    class Meta:
        model = Transaction
        fields = []
