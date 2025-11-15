"""
URL patterns for the NPL app.

Routes are organized by pipeline stage.  The feedback endpoints live in the
``feedback`` app and are included separately from the project urls.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    DocumentUploadView,
    DocumentViewSet,
    SpanViewSet,
    DocTypeRuleViewSet,
    SpanRuleViewSet,
    SpanEmbeddingViewSet,
)

router = DefaultRouter()
router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"spans", SpanViewSet, basename="span")
router.register(r"doctype-rules", DocTypeRuleViewSet, basename="doctype-rule")
router.register(r"span-rules", SpanRuleViewSet, basename="span-rule")
if SpanEmbeddingViewSet:
    router.register(r"span-embeddings", SpanEmbeddingViewSet, basename="span-embedding")

urlpatterns = [
    path('docs/upload', views.DocumentUploadView.as_view(), name='document-upload'),
    path('docs/<int:pk>/label/weak', views.WeakLabelView.as_view(), name='weak-label'),
    path('docs/<int:pk>/events/suggest/apply', views.ApplyEventsView.as_view(), name='apply-events'),
    path('docs/<int:pk>/spans', views.SpanListView.as_view(), name='list-spans'),
    path('docs/<int:pk>/embedding-mode/', views.EmbeddingModeUpdateView.as_view(), name='docs-embedding-mode'),
    path('documents/<int:pk>/rerun_full_pipeline/', views.DocumentRerunFullPipelineView.as_view(), name='document-rerun-full'),
    path('documents/<int:pk>/rerun_doctype_spans/', views.DocumentRerunDoctypeSpansView.as_view(), name='document-rerun-labels'),
    path('search', views.SearchView.as_view(), name='search'),
    path('pricing/run', views.PricingRunView.as_view(), name='pricing-run'),
    path("", include(router.urls)),
]