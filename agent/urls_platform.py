"""Platform-level (non-tenant) URL config for the agent app.

Mounted at ``/api/agent/`` from :mod:`nord_backend.urls`. Holds the
endpoints that are intentionally tenant-agnostic:

* ``connection/*`` — superuser-only OAuth lifecycle.
* ``connection/import-tokens/`` — superuser-only token import (CLI POST).
* ``tools/`` — read-only MCP tool catalog (any auth user).

Conversations + chat live in :mod:`agent.urls_tenant`, which IS mounted
under the ``/<tenant>/`` prefix so ``TenantMiddleware`` populates
``request.tenant``.
"""
from django.urls import path

from .views import (
    AgentToolCatalogView,
    OpenAIConnectionImportTokensView,
    OpenAIConnectionView,
)

urlpatterns = [
    path("connection/", OpenAIConnectionView.as_view(), name="agent-connection"),
    path(
        "connection/import-tokens/",
        OpenAIConnectionImportTokensView.as_view(),
        name="agent-connection-import-tokens",
    ),
    path("tools/", AgentToolCatalogView.as_view(), name="agent-tools"),
]
