"""Shared DRF permission classes used across the platform-admin surface.

Separate from ``api_utils`` because these are *policy* (who can do what)
rather than helpers for serialising or bulk ops. Kept small on purpose —
if you're reaching for a third class here, it probably belongs in the
per-app views instead.
"""

from __future__ import annotations

from rest_framework import permissions


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
