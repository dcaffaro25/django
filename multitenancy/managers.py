from django.db import models

class TenantAwareManager(models.Manager):
    """
    Manager to handle tenant-specific and cross-tenant queries.
    """

    def for_tenant(self, tenant):
        """
        Returns a queryset filtered by the current tenant.
        """
        if tenant is None:
            raise ValueError("Tenant cannot be None for tenant-aware queries.")
        return self.get_queryset().filter(company=tenant)

    def all_tenants(self, user):
        """
        Returns all records across tenants. Restricted to superusers only.
        """
        if not user.is_superuser:
            raise PermissionError("Only superusers can access all tenant data.")
        return self.get_queryset()