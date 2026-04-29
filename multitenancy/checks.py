"""Django system-check hooks for multitenancy/auth invariants.

Run automatically by ``manage.py check`` and on server startup. Errors
here block startup; warnings just log. The point is to catch
configuration mistakes that turn the app into a security hole — most
notably ``AUTH_OFF=True`` slipping into a non-DEBUG environment.
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Tags, register


@register(Tags.security)
def auth_off_only_in_debug(app_configs, **kwargs):
    """``AUTH_OFF=True`` bypasses every viewset's ``permission_classes``
    in code (e.g. ``if settings.AUTH_OFF: permission_classes = []``).
    That's only OK in a DEBUG environment with no real user data. If
    DEBUG is False we refuse to start so the flag can never silently
    open a production tenant to anonymous reads/writes.
    """
    errors = []
    if getattr(settings, "AUTH_OFF", False) and not getattr(settings, "DEBUG", True):
        errors.append(
            Error(
                "AUTH_OFF=True with DEBUG=False — refusing to start. "
                "This flag bypasses authentication on every viewset that "
                "guards itself with ``if settings.AUTH_OFF: "
                "permission_classes = []``.",
                hint=(
                    "Set ``AUTH_OFF=False`` in your production settings / "
                    "environment. The flag is intended for local development "
                    "only."
                ),
                id="multitenancy.E001",
            )
        )
    return errors
