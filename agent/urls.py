"""Aggregated URL config for the Sysnord agent app.

The actual URL definitions live in two sibling modules:

* :mod:`agent.urls_platform` — platform-wide endpoints (connection,
  tools). Mounted at ``/api/agent/`` from ``nord_backend.urls``.
* :mod:`agent.urls_tenant` — tenant-scoped endpoints (conversations,
  chat). Mounted at ``/<tenant_id>/api/agent/`` from
  ``nord_backend.urls`` so ``TenantMiddleware`` resolves the tenant.

This module is kept around for backwards compatibility — anything that
used to ``include('agent.urls')`` now gets the platform routes. The
tenant routes must be wired separately in ``nord_backend/urls.py`` to
get ``request.tenant``.
"""
from .urls_platform import urlpatterns  # noqa: F401
