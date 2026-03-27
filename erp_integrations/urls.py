"""
Legacy mount: /<tenant>/api/... when this module is included at /<tenant>/.

Primary resolution is via accounting/urls.py (merged api/ includes).
"""

from django.urls import include, re_path

urlpatterns = [
    re_path(r"api/", include("erp_integrations.api_urls")),
]
