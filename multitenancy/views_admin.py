"""Platform-admin endpoints under ``/api/admin/*``.

Everything here is gated by :class:`multitenancy.permissions.IsSuperUser`
and is explicitly **cross-tenant** — the middleware adds a tenant
segment to most project URLs, but these endpoints are mounted at the
project root (no tenant prefix) because platform admins need to see
the whole fleet.

Kept separate from ``multitenancy.views`` so a future ``admin`` Django
app can take this over without another giant rename.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.db.models import Prefetch
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from multitenancy.models import Company, UserCompanyMembership
from multitenancy.permissions import IsSuperUser


User = get_user_model()


# ------------------------------------------------------------------ serializers


class UserCompanyMembershipSerializer(serializers.ModelSerializer):
    """Flat shape for the nested list of companies a user belongs to.

    Includes a small ``company`` read-only snapshot so the UI doesn't
    need a second round-trip per row.
    """

    company_name = serializers.CharField(source="company.name", read_only=True)
    company_subdomain = serializers.CharField(source="company.subdomain", read_only=True)

    class Meta:
        model = UserCompanyMembership
        fields = [
            "id",
            "company",
            "company_name",
            "company_subdomain",
            "role",
            "is_primary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin-facing shape of :class:`CustomUser`.

    The main list view uses this — it embeds memberships so the admin
    table can show "belongs to N companies" and drill in without a
    follow-up request. Password is write-only (set/reset flows have
    dedicated actions below).
    """

    companies = UserCompanyMembershipSerializer(
        source="company_memberships", many=True, read_only=True
    )
    # Write-side convenience: accept a list of {company, role,
    # is_primary} dicts during create/update and reconcile the nested
    # memberships in one atomic transaction. Reads still use the
    # ``companies`` field above.
    set_companies = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "date_joined",
            "must_change_password",
            "companies",
            "set_companies",
            "password",
        ]
        read_only_fields = ["id", "last_login", "date_joined", "companies"]

    def create(self, validated_data: dict[str, Any]) -> Any:
        set_companies = validated_data.pop("set_companies", None)
        password = validated_data.pop("password", None)
        with db_transaction.atomic():
            user = User(**validated_data)
            if password:
                user.set_password(password)
            else:
                # Unusable password: operator must send an invite email or
                # "reset password" action before this account can log in.
                user.set_unusable_password()
                user.must_change_password = True
            user.save()
            if set_companies:
                _sync_memberships(user, set_companies)
        return user

    def update(self, instance, validated_data: dict[str, Any]) -> Any:
        set_companies = validated_data.pop("set_companies", None)
        password = validated_data.pop("password", None)
        with db_transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            if password:
                instance.set_password(password)
                instance.must_change_password = False
            instance.save()
            if set_companies is not None:
                _sync_memberships(instance, set_companies)
        return instance


def _sync_memberships(user, rows: list[dict]) -> None:
    """Reconcile UserCompanyMembership rows for ``user`` against ``rows``.

    Treats the caller's list as the full desired state: anything not in
    ``rows`` is deleted, anything new is created, existing rows get
    their role/is_primary updated. Enforces exactly-one ``is_primary``
    by demoting stale ones before writing.
    """
    wanted: dict[int, dict] = {}
    for r in rows:
        try:
            company_id = int(r.get("company"))
        except (TypeError, ValueError):
            continue
        wanted[company_id] = {
            "role": r.get("role") or UserCompanyMembership.ROLE_OPERATOR,
            "is_primary": bool(r.get("is_primary")),
        }

    # Drop rows the caller removed.
    UserCompanyMembership.objects.filter(user=user).exclude(company_id__in=wanted.keys()).delete()

    # Upsert the rest.
    for company_id, data in wanted.items():
        UserCompanyMembership.objects.update_or_create(
            user=user, company_id=company_id, defaults=data,
        )

    # At most one primary — if the caller sent multiple, keep the first
    # and drop the rest; if they sent none, leave whatever was there (no
    # silent demotion).
    primary_ids = [
        cid for cid, data in wanted.items() if data["is_primary"]
    ]
    if len(primary_ids) > 1:
        UserCompanyMembership.objects.filter(user=user).exclude(company_id=primary_ids[0]).update(is_primary=False)


# ---------------------------------------------------------------------- viewset


class UserAdminViewSet(viewsets.ModelViewSet):
    """Cross-tenant CRUD over platform users, gated to superusers.

    Mounted at ``/api/admin/users/`` (no tenant prefix). The stock
    ``list``/``retrieve``/``create``/``update``/``destroy`` methods
    handle the normal lifecycle; the extra ``@action``s below cover
    the two flows that would otherwise require multiple round-trips:
    password reset (returns the new password once, no persistence)
    and deactivation (soft toggle on ``is_active``).
    """

    queryset = (
        User.objects.all()
        .prefetch_related(
            Prefetch(
                "company_memberships",
                queryset=UserCompanyMembership.objects.select_related("company"),
            )
        )
        .order_by("username")
    )
    serializer_class = AdminUserSerializer
    permission_classes = [IsSuperUser]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        if q:
            qs = qs.filter(username__icontains=q) | qs.filter(email__icontains=q)
        return qs

    def perform_destroy(self, instance):
        """Soft-delete: deactivation, not row removal.

        Hard-deleting a user cascades into their historic attributions
        (created_by / updated_by across nearly every tenant-aware table)
        which wrecks audit trails. Prefer `is_active=False` and keep
        the row around.
        """
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="reset_password")
    def reset_password(self, request, pk=None):
        """Generate a fresh random password and return it *once*.

        The admin is expected to hand this off out-of-band (chat, SMS,
        whatever). Nothing is emailed by this endpoint — mail flows
        are separate and opt-in. Sets ``must_change_password`` so the
        user is forced to pick their own on next login.
        """
        user = self.get_object()
        # 16 chars from a URL-safe alphabet — strong enough for a
        # short-lived handoff token without being uncomfortable to
        # read back over a call.
        alphabet = string.ascii_letters + string.digits
        new_password = "".join(secrets.choice(alphabet) for _ in range(16))
        user.set_password(new_password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])
        return Response({
            "user_id": user.id,
            "username": user.username,
            "temporary_password": new_password,
            "must_change_password": True,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="set_active")
    def set_active(self, request, pk=None):
        """Toggle ``is_active``. Body: ``{"is_active": true|false}``."""
        user = self.get_object()
        desired = bool(request.data.get("is_active"))
        user.is_active = desired
        user.save(update_fields=["is_active"])
        return Response({"id": user.id, "is_active": user.is_active})


# ----------------------------------------------------- tiny company lookup

class AdminCompanyLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "subdomain"]


class AdminCompanyLookupViewSet(viewsets.ReadOnlyModelViewSet):
    """Flat list of all companies, visible only to superusers.

    The user-admin drawer needs a combobox of every company to assign
    memberships. Existing tenant-scoped company endpoints are
    filtered to the current subdomain, which is useless here. This is
    read-only on purpose — company CRUD has its own flow.
    """

    queryset = Company.objects.order_by("name")
    serializer_class = AdminCompanyLookupSerializer
    permission_classes = [IsSuperUser]
    pagination_class = None
