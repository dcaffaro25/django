"""URL configuration for the Sysnord agent app.

Two prefixes mounted under ``/api/agent/``:

* ``connection/*`` — superuser-only OAuth lifecycle.
* ``conversations/*`` — tenant-user-scoped chat.
* ``tools/`` — read-only MCP tool catalog (widget hint).
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgentConversationViewSet,
    AgentToolCatalogView,
    OpenAIConnectionCallbackView,
    OpenAIConnectionStartView,
    OpenAIConnectionView,
)

router = DefaultRouter()
router.register(r"conversations", AgentConversationViewSet, basename="agent-conversation")

urlpatterns = [
    path("connection/", OpenAIConnectionView.as_view(), name="agent-connection"),
    path("connection/start/", OpenAIConnectionStartView.as_view(), name="agent-connection-start"),
    path(
        "connection/callback/",
        OpenAIConnectionCallbackView.as_view(),
        name="agent-connection-callback",
    ),
    path("tools/", AgentToolCatalogView.as_view(), name="agent-tools"),
    path("", include(router.urls)),
]
