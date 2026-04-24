"""URL config for the ETL branch of v2 imports.

Mounted at ``/api/core/etl/v2/``. Legacy ETL endpoints stay at
``/api/core/etl/analyze/``, ``/api/core/etl/preview/``,
``/api/core/etl/execute/`` — this module does not touch them.

Shares ``commit`` and ``sessions`` views with the template branch
because those are mode-agnostic — ``session.mode`` drives the
divergent behaviour inside the service layer.
"""
from django.urls import path

from . import views

app_name = "imports_v2_etl"

urlpatterns = [
    path("analyze/", views.AnalyzeETLImportView.as_view(), name="analyze-etl"),
    path("commit/<int:pk>/", views.CommitSessionView.as_view(), name="commit"),
    path("resolve/<int:pk>/", views.ResolveSessionView.as_view(), name="resolve"),
    # Static routes BEFORE the pk route — see template_urls.py for why.
    path("sessions/running-count/", views.ImportSessionRunningCountView.as_view(), name="sessions-running-count"),
    path("sessions/", views.ImportSessionListView.as_view(), name="sessions-list"),
    path("sessions/<int:pk>/", views.ImportSessionDetailView.as_view(), name="session-detail"),
]
