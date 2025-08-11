# NORD/accounting/urls.py

from django.urls import path, include
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
    journal_entry_schema
)
from multitenancy.views import EntityViewSet, EntityMiniViewSet, EntityTreeView, EntityDynamicTransposedView

# Create a router and register viewsets
router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet)
router.register(r'accounts', AccountViewSet)
router.register(r'cost_centers', CostCenterViewSet)
router.register(r'transactions', TransactionViewSet)
router.register(r'journal_entries', JournalEntryViewSet)
router.register(r'rules', RuleViewSet)
router.register(r'banks', BankViewSet)
router.register(r'bank_accounts', BankAccountViewSet)
router.register(r'bank_transactions', BankTransactionViewSet)
router.register(r'reconciliation', ReconciliationViewSet)
router.register(r'entities', EntityViewSet, basename='entity')
router.register(r'entities-mini', EntityMiniViewSet)
#router.register(r'reconciliation_dashboard', UnreconciledDashboardView)

# Add custom routes for specific actions or views
custom_routes = [
    # Transaction-specific actions
    path('transactions/<int:pk>/post/', TransactionViewSet.as_view({'post': 'post'}), name='transaction-post'),
    path('transactions/<int:pk>/unpost/', TransactionViewSet.as_view({'post': 'unpost'}), name='transaction-unpost'),
    path('transactions/<int:pk>/cancel/', TransactionViewSet.as_view({'post': 'cancel'}), name='transaction-cancel'),
    path('transactions/<int:pk>/create_balancing_entry/', TransactionViewSet.as_view({'post': 'create_balancing_entry'}), name='transaction-create-balancing-entry'),
    path('transactions/filtered/', TransactionViewSet.as_view({'get': 'filtered'}), name='transaction-filtered'),
    path('reconciliation-dashboard/', UnreconciledDashboardView.as_view(), name='reconciliation-dashboard'),
    path('schema/transaction/', transaction_schema, name='transaction-schema'),
    path('schema/journal-entry/', journal_entry_schema, name='journal-entry-schema'),
    # Account summary
    path('account_summary/', AccountSummaryView.as_view(), name='account-summary'),

    # Entity tree for multitenancy
    path('entities-dynamic-transposed/', EntityDynamicTransposedView.as_view(), name='entity-dynamic-transposed'),
    path('entity-tree/<int:company_id>/', EntityTreeView.as_view(), name='entity-tree'),
]

# Combine router URLs and custom routes
urlpatterns = [
    path('api/', include(router.urls)),
    path('api/', include(custom_routes))
]
