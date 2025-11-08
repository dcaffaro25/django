"""
URL patterns for the NPL app.

Routes are organized by pipeline stage.  The feedback endpoints live in the
``feedback`` app and are included separately from the project urls.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('docs/upload', views.DocumentUploadView.as_view(), name='document-upload'),
    path('docs/<int:pk>/label/weak', views.WeakLabelView.as_view(), name='weak-label'),
    path('docs/<int:pk>/events/suggest/apply', views.ApplyEventsView.as_view(), name='apply-events'),
    path('docs/<int:pk>/spans', views.SpanListView.as_view(), name='list-spans'),
    path('search', views.SearchView.as_view(), name='search'),
    path('pricing/run', views.PricingRunView.as_view(), name='pricing-run'),
]