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
from .views import JobStatusView, JobListView, JobCancelView, TutorialView
from .task_views import (
    TaskListView, TaskDetailView, TaskStopView,
    TaskStatisticsView, TaskTypesView
)

from .chat.views import ChatAskView, ChatDiagView, ChatAskView_NoContext

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
    
    # Tutorial endpoint
    path("api/tutorial/", TutorialView.as_view(), name="tutorial"),
]
