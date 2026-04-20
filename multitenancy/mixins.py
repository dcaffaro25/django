# multitenancy/mixins.py
from django.http import Http404


def model_has_soft_delete(model):
    return any(getattr(f, "name", None) == "is_deleted" for f in model._meta.fields)


def apply_soft_delete_filter(qs, request):
    """
    Restrict queryset by is_deleted using the ``deleted`` query parameter:

    - Omitted or empty: only rows with ``is_deleted=False`` (default API behavior).
    - ``deleted=all``: all rows (no filter on ``is_deleted``).
    - ``deleted=only``: only rows with ``is_deleted=True``.

    If the model has no ``is_deleted`` field, ``qs`` is returned unchanged.
    """
    if qs is None:
        return qs
    model = qs.model
    if not model_has_soft_delete(model):
        return qs

    params = getattr(request, "query_params", None) or getattr(request, "GET", {})
    raw = (params.get("deleted") or "").strip().lower()
    if raw in ("all", "include", "true", "1", "yes"):
        return qs
    if raw in ("only", "soft", "deleted_only", "only_deleted"):
        return qs.filter(is_deleted=True)
    return qs.filter(is_deleted=False)


class SoftDeleteQuerysetMixin:
    """
    Apply :func:`apply_soft_delete_filter` after ``super().get_queryset()``.
    Use on viewsets that do *not* use :class:`ScopedQuerysetMixin` but whose
    model inherits ``BaseModel`` / ``TenantAwareBaseModel`` with ``is_deleted``.
    """

    def get_queryset(self):
        return apply_soft_delete_filter(super().get_queryset(), self.request)


class ScopedQuerysetMixin:
    """
    A reusable mixin that applies tenant and user scoping rules.
    - If request.user is superuser: return all records (optionally restricted by tenant).
    - If not superuser:
        - For CustomUser: only their own record.
        - For other models: restrict to current tenant if request.tenant exists.

    DELETE handling:
    When the model has an ``is_deleted`` field, ``perform_destroy`` **soft-deletes**
    by setting ``is_deleted=True`` instead of removing the row. Callers can opt in
    to a hard delete by passing ``?hard=1`` (superusers only — regular users cannot
    bypass the soft-delete safety net).
    """

    def perform_destroy(self, instance):
        model = type(instance)
        if not model_has_soft_delete(model):
            instance.delete()
            return
        hard = (
            str(self.request.query_params.get("hard", "")).lower() in ("1", "true", "yes")
            if hasattr(self.request, "query_params")
            else False
        )
        user = getattr(self.request, "user", None)
        if hard and user is not None and getattr(user, "is_superuser", False):
            instance.delete()
            return
        # Soft-delete path: mark the row and save just the flag + updated_at.
        instance.is_deleted = True
        update_fields = ["is_deleted"]
        if any(getattr(f, "name", None) == "updated_at" for f in model._meta.fields):
            from django.utils import timezone
            instance.updated_at = timezone.now()
            update_fields.append("updated_at")
        instance.save(update_fields=update_fields)

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # 🚨 Ensure the request has a tenant set by middleware
        tenant = getattr(self.request, "tenant", None)

        # 🔹 Superuser can see everything
        if user.is_superuser:
            if tenant and tenant != "all":
                qs = qs.filter(company=tenant)
            return apply_soft_delete_filter(qs, self.request)

        # 🔹 Regular user
        model = qs.model

        # If querying CustomUser, restrict to own record
        if model.__name__ == "CustomUser":
            qs = qs.filter(id=user.id)
            return apply_soft_delete_filter(qs, self.request)

        # Otherwise, restrict by tenant if available
        if tenant and tenant != "all":
            if hasattr(model, "company_id"):
                qs = qs.filter(company=tenant)
            elif hasattr(model, "entity") and hasattr(model.entity, "company_id"):
                qs = qs.filter(entity__company=tenant)
            else:
                # fallback: deny access if no tenant relation
                raise Http404("Tenant scoping not available for this model.")
            return apply_soft_delete_filter(qs, self.request)

        # Fallback: no tenant, just return empty set
        return apply_soft_delete_filter(qs.none(), self.request)

class TenantQuerysetMixin2:
    """
    A mixin to enforce tenant-based filtering on querysets.
    """

    def get_queryset(self):
        # Ensure 'tenant' is set on the request
        print('TenantQuerysetMixin:', self.request)
        if hasattr(self.request, 'tenant'):
            queryset = super().get_queryset()
            # Filter by company if the model has a `company` field
            if hasattr(queryset.model, 'company'):
                return queryset.filter(company=self.request.tenant)
            return queryset
        else:
            return super().get_queryset().none()
