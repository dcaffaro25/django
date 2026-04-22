# NORD/core/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FinancialIndexViewSet,
    IndexQuoteViewSet,
    FinancialIndexQuoteForecastViewSet,
    RecurrencePreviewView,
)
# core/urls.py
from django.urls import path
from core.views import ActivityFeedView, CeleryQueuesView, CeleryResultsView, CeleryTaskControlView
from core.views_activity import (
    ActivityBeaconView,
    AdminActivitySummaryView,
    AdminActivityEventsView,
    AdminActivityUserDetailView,
    AdminActivityAreaDetailView,
    AdminActivityFunnelsView,
    AdminActivityFrictionView,
    AdminActivityDigestRunView,
    AdminErrorReportsView,
    AdminErrorReportDetailView,
    AdminLedgerIntegrityView,
)
from .views import JobStatusView, JobListView, JobCancelView, TutorialView
from .task_views import (
    TaskListView, TaskDetailView, TaskStopView,
    TaskStatisticsView, TaskTypesView
)

from .chat.views import ChatAskView, ChatDiagView, ChatAskView_NoContext
from .chat.flexible_chat import FlexibleChatView

router = DefaultRouter()
router.trailing_slash = r'/?'

router.register(r'financial_indices', FinancialIndexViewSet)
router.register(r'index_quotes', IndexQuoteViewSet)
router.register(r'index_forecasts', FinancialIndexQuoteForecastViewSet)

custom_routes = [
    path(r'^rrule_preview/?$', RecurrencePreviewView.as_view(), name='rrule-preview'),
]

urlpatterns = [
    path(r'^api/?$', include(router.urls)),
    path(r'^api/?$', include(custom_routes)),
    path("api/activity/", ActivityFeedView.as_view(), name="activity-feed"),
    # Activity beacon (write): authenticated users POST their own
    # session + events here. Separate from the legacy "activity feed"
    # above — this one ingests tab-level telemetry.
    path("api/activity/batch/", ActivityBeaconView.as_view(), name="activity-beacon"),
    # Platform-admin reads — tenant-free, superuser-gated.
    path("api/admin/activity/summary/", AdminActivitySummaryView.as_view(), name="admin-activity-summary"),
    path("api/admin/activity/events/", AdminActivityEventsView.as_view(), name="admin-activity-events"),
    path("api/admin/activity/users/<int:user_id>/", AdminActivityUserDetailView.as_view(), name="admin-activity-user-detail"),
    path("api/admin/activity/areas/<str:area>/", AdminActivityAreaDetailView.as_view(), name="admin-activity-area-detail"),
    path("api/admin/activity/funnels/", AdminActivityFunnelsView.as_view(), name="admin-activity-funnels"),
    path("api/admin/activity/friction/", AdminActivityFrictionView.as_view(), name="admin-activity-friction"),
    path("api/admin/activity/digest/run/", AdminActivityDigestRunView.as_view(), name="admin-activity-digest-run"),
    path("api/admin/activity/errors/", AdminErrorReportsView.as_view(), name="admin-error-list"),
    path("api/admin/activity/errors/<int:report_id>/", AdminErrorReportDetailView.as_view(), name="admin-error-detail"),
    # Accounting integrity: PR 8's canary. Surfaces how many
    # Transactions still have the pre-PR-8 missing-cash-leg bug.
    path("api/admin/integrity/ledger/", AdminLedgerIntegrityView.as_view(), name="admin-ledger-integrity"),
    path("api/celery/queues/", CeleryQueuesView.as_view(), name="celery-queues"),
    path("api/celery/results/", CeleryResultsView.as_view(), name="celery-results"),
    path("api/celery/tasks/<uuid:task_id>/<str:action>/", CeleryTaskControlView.as_view(), name="celery-task-control"),
    # Legacy job endpoints (backwards compatible)
    path("jobs/", JobListView.as_view()),
    path("jobs/<str:task_id>/", JobStatusView.as_view()),
    path("jobs/<str:task_id>/cancel/", JobCancelView.as_view()),
    
    # New centralized task management endpoints
    path("api/tasks/", TaskListView.as_view(), name="task-list"),
    path("api/tasks/types/", TaskTypesView.as_view(), name="task-types"),
    path("api/tasks/statistics/", TaskStatisticsView.as_view(), name="task-statistics"),
    path("api/tasks/<str:task_id>/", TaskDetailView.as_view(), name="task-detail"),
    path("api/tasks/<str:task_id>/stop/", TaskStopView.as_view(), name="task-stop"),
    
    path("api/chat/ask/", ChatAskView.as_view()),
    path("api/chat/ask_nocontext/", ChatAskView.as_view()),
    path("api/chat/diag/", ChatDiagView.as_view()),
    path("api/chat/flexible/", FlexibleChatView.as_view(), name="flexible-chat"),
    
    # Tutorial endpoint
    path("api/tutorial/", TutorialView.as_view(), name="tutorial"),
]
