"""
Middleware for OpenClaw read-only enforcement.

When the ``openclaw_agent`` user makes a request, this middleware ensures
that only safe HTTP methods (GET, HEAD, OPTIONS) are allowed on business
endpoints.  The /api/meta/* introspection endpoints are always allowed.

To activate, add ``'api_meta.middleware.OpenClawReadOnlyMiddleware'``
to ``MIDDLEWARE`` in settings.py — AFTER authentication middleware.
"""
from django.http import JsonResponse

from .permissions import OPENCLAW_USERNAME, SAFE_METHODS


class OpenClawReadOnlyMiddleware:
    """Reject non-safe requests from the openclaw_agent user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user
            and user.is_authenticated
            and getattr(user, "username", None) == OPENCLAW_USERNAME
            and request.method not in SAFE_METHODS
            and not request.path.startswith("/api/meta/")
        ):
            return JsonResponse(
                {
                    "detail": (
                        "The OpenClaw read-only token does not permit "
                        f"{request.method} requests on this resource."
                    ),
                    "error_code": "OPENCLAW_READONLY",
                },
                status=403,
            )
        return self.get_response(request)
