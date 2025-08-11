# NORD/core/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FinancialIndexViewSet,
    IndexQuoteViewSet,
    FinancialIndexQuoteForecastViewSet,
    RecurrencePreviewView,
)

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
]