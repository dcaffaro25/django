"""Promote the platform-admin users to ``is_superuser=True``.

The new ``/admin/*`` React area is gated entirely by
``user.is_superuser``. Right now ``dcaffaro`` is a regular user and
would be locked out of the admin tooling we're building on top of this
migration — so we flip the flag idempotently here.

``nord-admin`` is already a superuser; included in the list as a
defensive no-op so the set of platform admins lives in one place.

Intentionally not changing ``is_staff`` — we don't use Django's own
``/admin/`` panel for this (per product decision), so the flag isn't
required. If that ever changes, flip it in a follow-up migration.
"""

from django.db import migrations


PLATFORM_ADMIN_USERNAMES = ("dcaffaro", "nord-admin")


def promote(apps, _schema_editor):
    User = apps.get_model("multitenancy", "CustomUser")
    User.objects.filter(username__in=PLATFORM_ADMIN_USERNAMES).update(
        is_superuser=True,
    )


def demote(apps, _schema_editor):
    """Safe reverse: only drops ``dcaffaro`` back. Leaves ``nord-admin``
    alone on the assumption it was already a superuser before this
    migration (forward is idempotent for that user)."""
    User = apps.get_model("multitenancy", "CustomUser")
    User.objects.filter(username="dcaffaro").update(is_superuser=False)


class Migration(migrations.Migration):

    dependencies = [
        ("multitenancy", "0032_rename_cliente_erp_id_to_erp_id"),
    ]

    operations = [
        migrations.RunPython(promote, reverse_code=demote),
    ]
