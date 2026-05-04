import logging

from django.http import JsonResponse
from django.urls import resolve
from .models import Company, UserCompanyMembership
from django.http import Http404
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .utils import resolve_tenant

log = logging.getLogger(__name__)

# HTTP methods that read state. Anything outside this set is a
# mutation and must be gated by role above ``viewer``.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Role ordering. Higher rank == more privileges. Used by the
# write-method gate below and by the ``TenantRolePermission`` class
# in ``multitenancy.permissions``. Mirror of
# ``UserCompanyMembership.ROLE_*``; kept inline so the middleware
# doesn't have to import the (cached) values dynamically.
_ROLE_RANK = {
    UserCompanyMembership.ROLE_VIEWER: 1,
    UserCompanyMembership.ROLE_OPERATOR: 2,
    UserCompanyMembership.ROLE_MANAGER: 3,
    UserCompanyMembership.ROLE_OWNER: 4,
}
_MIN_WRITE_RANK = _ROLE_RANK[UserCompanyMembership.ROLE_OPERATOR]


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Per-request path/headers tracing was useful during the
        # multitenancy bring-up but is now multiple kB per request on
        # Railway logs (auth tokens included). Demoted to ``DEBUG``
        # so it stays available behind the standard logging knob and
        # off in production by default.
        if log.isEnabledFor(logging.DEBUG):
            log.debug("TenantMiddleware path=%s", request.path)
            log.debug("TenantMiddleware headers=%s", dict(request.headers))

        if request.path.startswith('/login'):
            return self.get_response(request)
        
        # Bypass tenant check for admin, login/logout, or core API paths
        if (
            request.path.startswith('/admin') or
            request.path.startswith('/home') or
            request.path.startswith('/api/login') or
            request.path.startswith('/api/logout') or
            request.path.startswith('/api/core') or
            request.path.startswith('/api/meta') or
            # Agent /connection/ + /tools/ are platform-wide (superuser
            # admin + read-only catalog). Conversations + chat live under
            # /<tenant>/api/agent/ and DO need tenant resolution — this
            # bypass only matches the platform routes.
            request.path.startswith('/api/agent/connection') or
            request.path.startswith('/api/agent/tools') or
            request.path.startswith('/docs') or
            '/knowledge-base' in request.path
        ):
            return self.get_response(request)

        # Extract the tenant identifier
        path_parts = request.path_info.strip('/').split('/')
        subdomain = path_parts[0] if path_parts else None
        #print(subdomain)
        
        # Check if the user is authenticated
        if not request.user.is_authenticated and subdomain != 'testco':
            try:
                auth = TokenAuthentication()
                auth_result = auth.authenticate(request)
                if auth_result is not None:
                    user, token = auth_result
                    request.user = user
                    request.auth = token
            except AuthenticationFailed:
                # Don't return 401 here - let the view handle permissions
                # Some views (like knowledge-base) allow unauthenticated access
                # Just log and continue - the view's permission_classes will decide
                log.info(
                    "TenantMiddleware: auth failed for %s; allowing request "
                    "to continue (view's permission_classes will decide)",
                    request.path,
                )

        # Handle 'all' tenants for superusers
        if subdomain == 'all':
            if request.user.is_superuser:
                request.tenant = 'all'
            else:
                raise Http404("Not authorized to view all tenants")
        else:
            # Fetch tenant by subdomain
            try:
                request.tenant = resolve_tenant(subdomain)
            except Company.DoesNotExist:
                raise Http404("Company not found")

            # Membership check: an authenticated non-superuser may only
            # touch the tenant(s) they're a member of via
            # ``UserCompanyMembership``. Without this, the URL prefix
            # alone decides which tenant a request lands on -- a user
            # authenticated for tenant A could call ``/tenant_b/...``
            # and ``ScopedQuerysetMixin`` would happily serve them
            # tenant_b's data. We 404 (not 403) so a probing client
            # can't tell the difference between "tenant doesn't exist"
            # and "tenant exists but you're not a member".
            #
            # Unauthenticated requests fall through unchanged -- DRF's
            # ``IsAuthenticated`` on each viewset will reject them. The
            # legacy ``testco`` dev escape hatch (above) also flows
            # through unaffected because ``request.user`` stays
            # ``AnonymousUser`` for those.
            if (
                request.user.is_authenticated
                and not request.user.is_superuser
                and request.tenant is not None
                and request.tenant != 'all'
            ):
                # Single query: fetch the membership row's role
                # alongside the existence check. Annotate
                # ``request.user_role`` for downstream consumers
                # (TenantRolePermission, /api/core/me/, audit logs).
                membership = (
                    UserCompanyMembership.objects
                    .filter(user=request.user, company=request.tenant)
                    .values_list('role', flat=True)
                    .first()
                )
                if membership is None:
                    log.warning(
                        "TenantMiddleware: user %s denied access to tenant "
                        "%s (no membership)",
                        request.user.pk,
                        getattr(request.tenant, 'subdomain', request.tenant),
                    )
                    raise Http404("Company not found")
                request.user_role = membership

                # Global write gate: ``viewer`` role can only call
                # safe methods. Without this every viewset would have
                # to thread its own role check; doing it once at the
                # middleware layer means even a forgotten viewset is
                # safe-by-default.
                if (
                    request.method not in _SAFE_METHODS
                    and _ROLE_RANK.get(membership, 0) < _MIN_WRITE_RANK
                ):
                    log.info(
                        "TenantMiddleware: viewer %s blocked from %s %s",
                        request.user.pk, request.method, request.path,
                    )
                    return JsonResponse(
                        {"detail": "Read-only access for this role."},
                        status=403,
                    )
            elif request.user.is_authenticated and request.user.is_superuser:
                # Superuser metadata for the /api/core/me/ endpoint.
                request.user_role = "superuser"
        #print(request.tenant)
        return self.get_response(request)
