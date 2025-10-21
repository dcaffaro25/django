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
from .views import JobStatusView, JobListView, JobCancelView

from .chat.views import ChatAskView

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
    path("jobs/", JobListView.as_view()),
    path("jobs/<str:task_id>/", JobStatusView.as_view()),
    path("jobs/<str:task_id>/cancel/", JobCancelView.as_view()),
    path("api/chat/ask/", ChatAskView.as_view()),
]
