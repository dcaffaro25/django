"""URL config for the TEMPLATE branch of v2 imports.

Mounted at ``/api/core/imports/v2/``. Legacy template endpoint stays
at ``/api/core/bulk-import/``.

The ETL branch lives in ``etl_urls.py`` and mounts at
``/api/core/etl/v2/``. Both branches share the ``commit`` and
``sessions`` views because those are mode-agnostic — the session's
``mode`` field drives the divergent behaviour inside the service
layer.
"""
from django.urls import path

from . import views

app_name = "imports_v2_template"

urlpatterns = [
    path("analyze/", views.AnalyzeTemplateImportView.as_view(), name="analyze-template"),
    path("commit/<int:pk>/", views.CommitSessionView.as_view(), name="commit"),
    path("sessions/<int:pk>/", views.ImportSessionDetailView.as_view(), name="session-detail"),
]
