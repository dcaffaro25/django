"""Shared DRF permission classes used across the platform-admin surface.

Separate from ``api_utils`` because these are *policy* (who can do what)
rather than helpers for serialising or bulk ops. Kept small on purpose —
if you're reaching for a third class here, it probably belongs in the
per-app views instead.
"""

from __future__ import annotations

from rest_framework import permissions

from .models import UserCompanyMembership


class IsSuperUser(permissions.BasePermission):
    """Allow only Django superusers.

    DRF's bundled :class:`~rest_framework.permissions.IsAdminUser` keys
    off ``is_staff``, which is a weaker concept (and one we don't
    grant to our platform admins — see migration
    ``multitenancy.0033_promote_platform_admins``). Use this class
    wherever an endpoint must be visible to dcaffaro-level admins
    only.
    """

    message = "Only platform admins can access this endpoint."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_superuser)


# Role hierarchy for ``UserCompanyMembership``. Higher rank == more
# privileges. The same ordering is duplicated in
# ``multitenancy.middleware`` for the global write-method gate; both
# must agree.
_ROLE_RANK = {
    UserCompanyMembership.ROLE_VIEWER: 1,
    UserCompanyMembership.ROLE_OPERATOR: 2,
    UserCompanyMembership.ROLE_MANAGER: 3,
    UserCompanyMembership.ROLE_OWNER: 4,
}


class IsTenantRoleAtLeast(permissions.BasePermission):
    """Permission factory: only allow users whose tenant role is at
    least ``min_role``. Use as ``IsTenantRoleAtLeast.with_min(min)``::

        permission_classes = [
            permissions.IsAuthenticated,
            IsTenantRoleAtLeast.with_min(UserCompanyMembership.ROLE_MANAGER),
        ]

    The middleware annotates ``request.user_role`` after the
    membership check; superusers come through as ``"superuser"`` and
    always pass. Anonymous users pass through to whatever
    ``IsAuthenticated`` decides (typically a 401).

    Most viewsets don't need this — the middleware's global
    write-method gate already keeps ``viewer`` users out of POST/
    PATCH/PUT/DELETE. Reach for ``IsTenantRoleAtLeast`` only when an
    *otherwise-readable* endpoint should be hidden from a lower role
    (e.g. the API sandbox playground or tenant-config viewer).
    """

    message = "Insufficient tenant role for this endpoint."

    @classmethod
    def with_min(cls, min_role: str):
        """Return a subclass that compares against ``min_role``."""
        if min_role not in _ROLE_RANK:
            raise ValueError(f"Unknown role: {min_role}")

        class _Bound(cls):
            _min_role = min_role
        _Bound.__name__ = f"IsTenantRoleAtLeast_{min_role}"
        return _Bound

    _min_role = UserCompanyMembership.ROLE_VIEWER

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        role = getattr(request, "user_role", None)
        if role is None:
            return False
        return _ROLE_RANK.get(role, 0) >= _ROLE_RANK[self._min_role]
