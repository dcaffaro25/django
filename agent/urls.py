"""URL configuration for the Sysnord agent app.

Mounted under ``/api/agent/`` from :mod:`nord_backend.urls`:

* ``connection/``                — superuser-only OAuth lifecycle.
  - GET  → status
  - DELETE → disconnect
* ``connection/import-tokens/``  — superuser-only POST that accepts the
  tokens produced by ``python manage.py openai_oauth_login``.
* ``conversations/*``            — tenant-user-scoped chat (CRUD + chat).
* ``tools/``                     — read-only MCP tool catalog.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgentConversationViewSet,
    AgentToolCatalogView,
    OpenAIConnectionImportTokensView,
    OpenAIConnectionView,
)

router = DefaultRouter()
router.register(r"conversations", AgentConversationViewSet, basename="agent-conversation")

urlpatterns = [
    path("connection/", OpenAIConnectionView.as_view(), name="agent-connection"),
    path(
        "connection/import-tokens/",
        OpenAIConnectionImportTokensView.as_view(),
        name="agent-connection-import-tokens",
    ),
    path("tools/", AgentToolCatalogView.as_view(), name="agent-tools"),
    path("", include(router.urls)),
]
