"""Project-level views. Keep narrow — app-specific views live in each
Django app's own ``views.py``. Two things here right now:

  * :func:`index` — serves the built SPA's ``index.html``.
  * :class:`CurrentUserView` — minimal ``GET /api/auth/me/`` endpoint
    the frontend ``AuthProvider`` calls to populate the session's
    user profile (including ``is_superuser`` for the admin gate).
    Added as part of the runtime-config work after noticing the SPA
    fell back to a hardcoded ``{username: "dev"}`` placeholder when
    this endpoint didn't exist, which silently broke the
    ``SuperuserGuard``.
"""
from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def index(request):
    return render(request, 'index.html')


class CurrentUserView(APIView):
    """``GET /api/auth/me/``

    Returns the authenticated user's profile. Deliberately narrow —
    just what the SPA needs to render the header + gate admin
    routes. Any richer profile data (preferences, tenant
    memberships, etc.) lives on dedicated endpoints.

    Shape must stay in sync with the ``User`` interface in
    ``frontend/src/providers/AuthProvider.tsx`` — specifically
    ``is_superuser`` is the single field the superuser gate reads.

    401 when unauthenticated (not 403) — the SPA interprets a
    missing profile as "log in required", not "you're in but
    forbidden".
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response({
            "id": u.pk,
            "username": u.get_username(),
            "email": getattr(u, "email", "") or None,
            "first_name": getattr(u, "first_name", "") or "",
            "last_name": getattr(u, "last_name", "") or "",
            "is_superuser": bool(getattr(u, "is_superuser", False)),
            "is_staff": bool(getattr(u, "is_staff", False)),
            # Convenience for the sidebar's "Olá, <name>" greeting —
            # full name if set, else username. The frontend already
            # computes this client-side but inlining here means one
            # less round of branching on the UI side.
            "display_name": (
                (u.get_full_name() or "").strip()
                or u.get_username()
            ),
        })
