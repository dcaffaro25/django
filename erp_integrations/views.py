from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.mixins import ScopedQuerysetMixin

from .erp_etl import execute_erp_etl_import
from .models import ERPAPIDefinition, ERPConnection
from .serializers import (
    BuildPayloadRequestSerializer,
    ERPAPIDefinitionSerializer,
    ERPConnectionListSerializer,
    ERPConnectionSerializer,
    ErpEtlImportRequestSerializer,
)
from .services.payload_builder import build_payload_by_ids


class ERPConnectionViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for tenant-scoped ERP connections (app_key, app_secret)."""

    queryset = ERPConnection.objects.select_related("provider", "company").order_by("provider__slug")

    def get_serializer_class(self):
        if self.action == "list":
            return ERPConnectionListSerializer
        return ERPConnectionSerializer


class ERPAPIDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of API definitions (global, not tenant-scoped)."""

    queryset = ERPAPIDefinition.objects.filter(is_active=True).select_related("provider").order_by("provider__slug", "call")
    serializer_class = ERPAPIDefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        provider_id = self.request.query_params.get("provider")
        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        return qs


class BuildPayloadView(APIView):
    """POST build-payload: build ERP API request JSON (call, param, app_key, app_secret)."""

    def post(self, request, tenant_id=None):
        serializer = BuildPayloadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = None
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            company_id = tenant.id

        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required to build payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = build_payload_by_ids(
                connection_id=data["connection_id"],
                api_definition_id=data["api_definition_id"],
                param_overrides=data.get("param_overrides") or {},
                company_id=company_id,
            )
        except ERPConnection.DoesNotExist:
            return Response(
                {"detail": "Connection not found or not accessible for this tenant."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ERPAPIDefinition.DoesNotExist:
            return Response(
                {"detail": "API definition not found or does not match connection provider."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"payload": payload}, status=status.HTTP_200_OK)


class ErpEtlImportView(APIView):
    """
    POST: Run ERP API ETL import (preview or commit).
    Body: { "mapping_id": int, "response": { ... }, "commit": bool }.
    Same flow as Excel ETL: preview first, then commit when ready.
    """

    def post(self, request, tenant_id=None):
        serializer = ErpEtlImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required for ERP ETL import."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = execute_erp_etl_import(
            company_id=company_id,
            response_payload=data["response"],
            mapping_id=data["mapping_id"],
            commit=data.get("commit", False),
            import_metadata={"source": "ErpEtlImportView", "function": "execute_erp_etl_import"},
        )
        # Early failure (mapping not found, no sheets)
        if result.get("errors"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        # Commit requested but transaction was rolled back (e.g. validation failed)
        if data.get("commit") and not result.get("committed"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
