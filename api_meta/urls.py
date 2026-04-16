"""
URL configuration for the Meta / Introspection API.

All endpoints live under /api/meta/ and are GET-only.
"""
from django.urls import path

from .views import (
    MetaCapabilitiesView,
    MetaDocsDetailView,
    MetaDocsListView,
    MetaEndpointsView,
    MetaEnumsView,
    MetaFiltersView,
    MetaHealthView,
    MetaModelDetailView,
    MetaModelRelationshipsView,
    MetaModelsListView,
)

urlpatterns = [
    path("endpoints/", MetaEndpointsView.as_view(), name="meta-endpoints"),
    path("models/", MetaModelsListView.as_view(), name="meta-models"),
    path("models/<str:model_name>/", MetaModelDetailView.as_view(), name="meta-model-detail"),
    path("models/<str:model_name>/relationships/", MetaModelRelationshipsView.as_view(), name="meta-model-relationships"),
    path("enums/", MetaEnumsView.as_view(), name="meta-enums"),
    path("filters/", MetaFiltersView.as_view(), name="meta-filters"),
    path("capabilities/", MetaCapabilitiesView.as_view(), name="meta-capabilities"),
    path("health/", MetaHealthView.as_view(), name="meta-health"),
    path("docs/", MetaDocsListView.as_view(), name="meta-docs-list"),
    path("docs/<path:doc_path>", MetaDocsDetailView.as_view(), name="meta-docs-detail"),
]
