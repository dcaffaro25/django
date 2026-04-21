"""Platform-admin URLs — mounted at ``/api/admin/`` by the project
urlconf. No tenant prefix; every endpoint here is gated by
:class:`multitenancy.permissions.IsSuperUser`.

Kept tiny by design — the admin surface should stay shallow so its
boundary is easy to audit. If something grows complex, push it into
its own app under ``admin/`` or a sibling ``platform_admin``.
"""

from rest_framework.routers import DefaultRouter

from .views_admin import UserAdminViewSet, AdminCompanyLookupViewSet


router = DefaultRouter()
router.register(r"users", UserAdminViewSet, basename="admin-user")
router.register(r"companies", AdminCompanyLookupViewSet, basename="admin-company")

urlpatterns = router.urls
