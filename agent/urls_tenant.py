"""Tenant-scoped URL config for the agent app.

Mounted at ``/<tenant_id>/api/agent/`` from :mod:`nord_backend.urls`,
which means :class:`multitenancy.middleware.TenantMiddleware` resolves
``<tenant_id>`` to ``request.tenant`` before the viewset runs. The
conversation viewset filters its queryset by both ``request.user`` and
``request.tenant`` to keep threads private per (user, company).
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AgentConversationViewSet

router = DefaultRouter()
router.register(r"conversations", AgentConversationViewSet, basename="agent-conversation")

urlpatterns = [
    path("", include(router.urls)),
]
