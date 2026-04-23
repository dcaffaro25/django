"""URL config for v2 imports, mounted under ``/api/core/imports/v2/``.

Legacy endpoints remain at ``/api/core/bulk-import/`` and the ETL
paths at ``/api/core/etl/...`` — this module does not touch them.
"""
from django.urls import path

from . import views

app_name = "imports_v2"

urlpatterns = [
    path("analyze/", views.AnalyzeTemplateImportView.as_view(), name="analyze-template"),
    path("commit/<int:pk>/", views.CommitSessionView.as_view(), name="commit"),
    path("sessions/<int:pk>/", views.ImportSessionDetailView.as_view(), name="session-detail"),
]
