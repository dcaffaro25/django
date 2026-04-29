"""Regression tests for the tenant-membership check in
``TenantMiddleware``.

The middleware sets ``request.tenant`` from the URL prefix
(``/<subdomain>/...``). Until we added a membership check, that
prefix alone was enough to pick a tenant — meaning a user
authenticated for tenant A could call ``/tenant_b/api/...`` and
``ScopedQuerysetMixin`` would happily serve them tenant_b's data.
These tests pin the new contract:

  * superuser → access any tenant
  * member of tenant via ``UserCompanyMembership`` → access that tenant
  * authenticated non-member → 404 (not 403, to avoid existence-leak)
  * unauthenticated → falls through to the view's permission_classes
    (we test that the middleware doesn't 404 anonymous users)
"""
from __future__ import annotations

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from multitenancy.models import (
    Company,
    CustomUser,
    UserCompanyMembership,
)


class TenantMembershipMiddlewareTests(TestCase):
    """The membership check sits inside ``TenantMiddleware``; we
    exercise it via the live request stack (APIClient) rather than
    calling the middleware directly so we cover the same path a real
    request would. URL we hit must exist *and* must be tenant-scoped
    -- ``/<subdomain>/api/accounts/`` qualifies."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Company.objects.create(name="Alpha Co", subdomain="alpha")
        cls.tenant_b = Company.objects.create(name="Beta Co", subdomain="beta")

        cls.member_user = CustomUser.objects.create_user(
            username="member_a", password="x", email="m@a.test",
        )
        UserCompanyMembership.objects.create(
            user=cls.member_user, company=cls.tenant_a,
            role=UserCompanyMembership.ROLE_VIEWER,
        )
        cls.member_token = Token.objects.create(user=cls.member_user)

        cls.superuser = CustomUser.objects.create_superuser(
            username="root", password="x", email="r@x.test",
        )
        cls.super_token = Token.objects.create(user=cls.superuser)

    def setUp(self):
        self.client = APIClient()

    def _auth(self, token: Token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_member_can_access_own_tenant(self):
        self._auth(self.member_token)
        # Any tenant-scoped path works; ``/api/entities-mini/`` returns
        # 200 with an empty list when the tenant has no entities.
        resp = self.client.get(f"/{self.tenant_a.subdomain}/api/entities-mini/")
        # The endpoint may legitimately return 200 (empty list) or
        # 401/403 if some unrelated permission gate kicks in; the
        # important assertion is "not a 404 from middleware".
        self.assertNotEqual(resp.status_code, 404, resp.content)

    def test_authenticated_non_member_gets_404_on_other_tenant(self):
        """The headline regression: cross-tenant data leak via URL."""
        self._auth(self.member_token)
        resp = self.client.get(f"/{self.tenant_b.subdomain}/api/entities-mini/")
        self.assertEqual(resp.status_code, 404)

    def test_superuser_bypasses_membership(self):
        self._auth(self.super_token)
        # Superuser hits both tenants without rows in
        # UserCompanyMembership.
        resp_a = self.client.get(f"/{self.tenant_a.subdomain}/api/entities-mini/")
        resp_b = self.client.get(f"/{self.tenant_b.subdomain}/api/entities-mini/")
        self.assertNotEqual(resp_a.status_code, 404, resp_a.content)
        self.assertNotEqual(resp_b.status_code, 404, resp_b.content)

    def test_unauthenticated_request_is_not_404d_by_middleware(self):
        """Unauthenticated requests should fall through the middleware
        unchanged — DRF's ``IsAuthenticated`` will reject them with a
        401 at the view layer. The middleware must not pre-empt that
        with a 404 because callers (login flows, public health
        checks) rely on the 401 signal."""
        # No credentials set.
        resp = self.client.get(f"/{self.tenant_a.subdomain}/api/entities-mini/")
        # 401 (Unauthorized) is the expected outcome on a viewset
        # whose permission_classes = [IsAuthenticated]. We assert it's
        # NOT 404 specifically (which would indicate the middleware
        # overstepped).
        self.assertNotEqual(resp.status_code, 404, resp.content)

    def test_unknown_tenant_returns_404(self):
        """The middleware's pre-existing ``Company.DoesNotExist → 404``
        path must keep working alongside the new membership check."""
        self._auth(self.member_token)
        resp = self.client.get("/no-such-tenant/api/entities-mini/")
        self.assertEqual(resp.status_code, 404)
