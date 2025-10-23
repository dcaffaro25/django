# NORD/accounting/urls.py

from django.urls import re_path, include
from rest_framework.routers import DefaultRouter
from django.urls import path
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
    ReconciliationTaskViewSet,
    ReconciliationViewSet,
    ReconciliationConfigViewSet,
)
from .views import (
    EmbeddingBackfillView,
    EmbeddingTaskStatusView,
    EmbeddingHealthView,
    EmbeddingMissingCountsView,
)
from .views import EmbeddingSemanticSearchView, EmbeddingJobsListView, EmbeddingHealthView, EmbeddingMissingCountsView, EmbeddingBackfillView, EmbeddingTaskStatusView, EmbeddingsTestView
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
router.register(r'reconciliation_configs', ReconciliationConfigViewSet, basename="reconciliation-configs")  # 👈 new

urlpatterns = [
    # IMPORTANT: no extra 'api/' here because the project urls already mount this file at /<tenant>/api/
    re_path(r'api/', include(router.urls)),

    # Custom routes  use re_path for optional trailing slash
    re_path(r'^transactions/(?P<pk>\d+)/post/?$',  TransactionViewSet.as_view({'post': 'post'}), name='transaction-post'),
    re_path(r'^transactions/(?P<pk>\d+)/unpost/?$', TransactionViewSet.as_view({'post': 'unpost'}), name='transaction-unpost'),
    re_path(r'^transactions/(?P<pk>\d+)/cancel/?$', TransactionViewSet.as_view({'post': 'cancel'}), name='transaction-cancel'),
    re_path(r'^transactions/(?P<pk>\d+)/create_balancing_entry/?$', TransactionViewSet.as_view({'post': 'create_balancing_entry'}), name='transaction-create-balancing-entry'),
    re_path(r'^transactions/filtered/?$', TransactionViewSet.as_view({'get': 'filtered'}), name='transaction-filtered'),

    re_path(r'^reconciliation-dashboard/?$', UnreconciledDashboardView.as_view(), name='reconciliation-dashboard'),
    re_path(r'^account_summary/?$', AccountSummaryView.as_view(), name='account-summary'),

    re_path(r'^entities-dynamic-transposed/?$', EntityDynamicTransposedView.as_view(), name='entity-dynamic-transposed'),
    re_path(r'^entity-tree/(?P<company_id>\d+)/?$', EntityTreeView.as_view(), name='entity-tree'),
    path("embeddings/health/", EmbeddingHealthView.as_view(), name="embeddings-health"),
    path("embeddings/missing-counts/", EmbeddingMissingCountsView.as_view(), name="embeddings-missing-counts"),
    path("embeddings/backfill/", EmbeddingBackfillView.as_view(), name="embeddings-backfill"),
    path("embeddings/tasks/<str:task_id>/", EmbeddingTaskStatusView.as_view(), name="embeddings-task-status"),
    path("embeddings/jobs/", EmbeddingJobsListView.as_view(), name="embedding-jobs-list"),
    path("embeddings/test/", EmbeddingsTestView.as_view(), name="embeddings-test"),
    path("embeddings/search/", EmbeddingSemanticSearchView.as_view(), name="embedding-semantic-search"),
]
