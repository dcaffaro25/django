# multitenancy/mixins.py
from django.http import Http404

class ScopedQuerysetMixin:
    """
    A reusable mixin that applies tenant and user scoping rules.
    - If request.user is superuser: return all records (optionally restricted by tenant).
    - If not superuser:
        - For CustomUser: only their own record.
        - For other models: restrict to current tenant if request.tenant exists.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        # 🚨 Ensure the request has a tenant set by middleware
        tenant = getattr(self.request, "tenant", None)

        # 🔹 Superuser can see everything
        if user.is_superuser:
            if tenant and tenant != "all":
                return qs.filter(company=tenant)
            return qs

        # 🔹 Regular user
        model = qs.model

        # If querying CustomUser, restrict to own record
        if model.__name__ == "CustomUser":
            return qs.filter(id=user.id)

        # Otherwise, restrict by tenant if available
        if tenant and tenant != "all":
            if hasattr(model, "company_id"):
                return qs.filter(company=tenant)
            elif hasattr(model, "entity") and hasattr(model.entity, "company_id"):
                return qs.filter(entity__company=tenant)
            # fallback: deny access if no tenant relation
            raise Http404("Tenant scoping not available for this model.")

        # Fallback: no tenant, just return empty set
        return qs.none()

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
