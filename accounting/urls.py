# NORD/accounting/urls.py

from django.urls import re_path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CurrencyViewSet,
    AccountViewSet,
    TransactionViewSet,
    JournalEntryViewSet,
    RuleViewSet,
    BankViewSet,
    CostCenterViewSet,
    BankAccountViewSet,
    BankTransactionViewSet,
    AccountSummaryView,
    ReconciliationViewSet,
    UnreconciledDashboardView,
    transaction_schema,
    journal_entry_schema,
    ReconciliationTaskViewSet,
)
from multitenancy.views import EntityViewSet, EntityMiniViewSet, EntityTreeView, EntityDynamicTransposedView

# Router that accepts with/without trailing slash
class LooseSlashRouter(DefaultRouter):
    trailing_slash = r'/?'

router = LooseSlashRouter()
router.register('currencies', CurrencyViewSet)
router.register('accounts', AccountViewSet)
router.register('cost_centers', CostCenterViewSet)
router.register('transactions', TransactionViewSet)
router.register('journal_entries', JournalEntryViewSet)
router.register('rules', RuleViewSet)
router.register('banks', BankViewSet)
router.register('bank_accounts', BankAccountViewSet)
router.register('bank_transactions', BankTransactionViewSet)
router.register('reconciliation', ReconciliationViewSet)
router.register('entities', EntityViewSet, basename='entity')
router.register('entities-mini', EntityMiniViewSet)
router.register(r"reconciliation-tasks", ReconciliationTaskViewSet, basename="reconciliationtask")

urlpatterns = [
    # IMPORTANT: no extra 'api/' here because the project urls already mount this file at /<tenant>/api/
    re_path(r'api/', include(router.urls)),

    # Custom routes — use re_path for optional trailing slash
    re_path(r'^transactions/(?P<pk>\d+)/post/?$',  TransactionViewSet.as_view({'post': 'post'}), name='transaction-post'),
    re_path(r'^transactions/(?P<pk>\d+)/unpost/?$', TransactionViewSet.as_view({'post': 'unpost'}), name='transaction-unpost'),
    re_path(r'^transactions/(?P<pk>\d+)/cancel/?$', TransactionViewSet.as_view({'post': 'cancel'}), name='transaction-cancel'),
    re_path(r'^transactions/(?P<pk>\d+)/create_balancing_entry/?$', TransactionViewSet.as_view({'post': 'create_balancing_entry'}), name='transaction-create-balancing-entry'),
    re_path(r'^transactions/filtered/?$', TransactionViewSet.as_view({'get': 'filtered'}), name='transaction-filtered'),

    re_path(r'^reconciliation-dashboard/?$', UnreconciledDashboardView.as_view(), name='reconciliation-dashboard'),
    re_path(r'^schema/transaction/?$', transaction_schema, name='transaction-schema'),
    re_path(r'^schema/journal-entry/?$', journal_entry_schema, name='journal-entry-schema'),
    re_path(r'^account_summary/?$', AccountSummaryView.as_view(), name='account-summary'),

    re_path(r'^entities-dynamic-transposed/?$', EntityDynamicTransposedView.as_view(), name='entity-dynamic-transposed'),
    re_path(r'^entity-tree/(?P<company_id>\d+)/?$', EntityTreeView.as_view(), name='entity-tree'),
]
