"""
OpenClaw-specific permissions.

The ``OpenClawReadOnlyToken`` is a long-lived API token that grants:
  - Full access to all GET endpoints (list/detail).
  - Full access to all /api/meta/* introspection endpoints.
  - Denial (403) for any mutating method (POST, PUT, PATCH, DELETE) on
    business resources.

Usage:
  1. Create a Django ``rest_framework.authtoken.models.Token`` for a
     dedicated ``CustomUser`` whose ``username`` is ``openclaw_agent``.
  2. The token is passed via the ``Authorization: Token <token>`` header,
     as with any other DRF TokenAuthentication consumer.
  3. Add ``IsOpenClawReadOnly`` to ``permission_classes`` on any viewset
     that should enforce read-only for the OpenClaw user, or rely on the
     global check in the middleware/view mixin.

The helper management command ``create_openclaw_token`` (see
``api_meta/management/commands/create_openclaw_token.py``) automates
creation of the agent user + token.
"""
from rest_framework.permissions import BasePermission

OPENCLAW_USERNAME = "openclaw_agent"

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class IsOpenClawReadOnly(BasePermission):
    """
    Allow full read access for the OpenClaw agent user.
    Deny any write method.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if getattr(request.user, "username", None) == OPENCLAW_USERNAME:
            if request.method in SAFE_METHODS:
                return True
            return False

        # For non-OpenClaw users, defer to other permission classes.
        return True
