# -*- coding: utf-8 -*-
"""
Inventory API views.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from multitenancy.mixins import ScopedQuerysetMixin

from .models import (
    Warehouse,
    UnitOfMeasure,
    UoMConversion,
    StockMovement,
    InventoryBalance,
    InventoryAlert,
)
from .serializers import (
    WarehouseSerializer,
    UnitOfMeasureSerializer,
    UoMConversionSerializer,
    StockMovementSerializer,
    InventoryBalanceSerializer,
    InventoryAlertSerializer,
)
from .services.movement_service import ingest_nf_to_movements, create_manual_adjustment
from .services.costing_engine import compute_for_strategies
from .services.valuation_service import (
    get_comparison_report,
    get_sku_drilldown,
    get_movement_drilldown,
)
from .services.anomaly_service import run_anomaly_detection


class WarehouseViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name"]


class UnitOfMeasureViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name"]


class UoMConversionViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = UoMConversion.objects.all()
    serializer_class = UoMConversionSerializer
    filterset_fields = ["product", "from_uom", "to_uom"]


class StockMovementViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only: movements are created by NF ingestion or manual adjustment service.
    """
    queryset = StockMovement.objects.select_related(
        "product", "warehouse", "uom", "nfe_item", "nota_fiscal"
    ).all()
    serializer_class = StockMovementSerializer
    filterset_fields = ["product", "warehouse", "movement_type", "source_type"]
    ordering_fields = ["movement_date", "created_at"]
    ordering = ["-movement_date"]

    @action(detail=False, methods=["post"])
    def manual(self, request):
        """Create a manual stock adjustment. Requires: product_id, quantity, optional: unit_cost, warehouse_id, reference."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product_id = request.data.get("product_id")
        quantity = request.data.get("quantity")
        if product_id is None or quantity is None:
            return Response(
                {"error": "product_id and quantity required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            return Response(
                {"error": "quantity must be a number"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        unit_cost = request.data.get("unit_cost")
        warehouse_id = request.data.get("warehouse_id")
        reference = request.data.get("reference", "")
        movement, err = create_manual_adjustment(
            company=tenant,
            product_id=product_id,
            quantity=quantity,
            unit_cost=unit_cost,
            warehouse_id=warehouse_id,
            reference=reference,
        )
        if err:
            return Response({"error": err}, status=status.HTTP_400_BAD_REQUEST)
        serializer = StockMovementSerializer(movement)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def ingest_nf(self, request):
        """Ingest NF-e items into stock movements. Body: {nota_fiscal_id?: int, nota_fiscal_ids?: [int]}."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        nota_fiscal_id = request.data.get("nota_fiscal_id")
        nota_fiscal_ids = request.data.get("nota_fiscal_ids")
        result = ingest_nf_to_movements(
            company=tenant,
            nota_fiscal_id=nota_fiscal_id,
            nota_fiscal_ids=nota_fiscal_ids,
        )
        return Response(result, status=status.HTTP_200_OK)


class InventoryBalanceViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InventoryBalance.objects.select_related("product", "warehouse").all()
    serializer_class = InventoryBalanceSerializer
    filterset_fields = ["product", "warehouse"]


class CostingComputeView(viewsets.ViewSet):
    """Trigger costing computation for strategies."""

    @action(detail=False, methods=["post"])
    def compute(self, request):
        """Run costing engine. Body: {strategy_keys?: [...], start_date?: str, end_date?: str}."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        strategy_keys = request.data.get("strategy_keys")
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        product_ids = request.data.get("product_ids")
        warehouse_ids = request.data.get("warehouse_ids")

        if start_date:
            from datetime import datetime
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            from datetime import datetime
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

        result = compute_for_strategies(
            company=tenant,
            strategy_keys=strategy_keys,
            start_date=start_date,
            end_date=end_date,
            product_ids=product_ids,
            warehouse_ids=warehouse_ids,
        )
        # Convert dataclasses to dicts for JSON
        from decimal import Decimal
        from datetime import date, datetime

        def _serialize(v):
            if isinstance(v, Decimal):
                return float(v)
            if isinstance(v, (date, datetime)):
                return v.isoformat()
            return v

        def _to_dict(obj):
            if hasattr(obj, "__dataclass_fields__"):
                return {k: _serialize(v) for k, v in vars(obj).items()}
            return obj
        out = {
            "valuations": {
                k: [_to_dict(v) for v in vals]
                for k, vals in result["valuations"].items()
            },
            "allocations": {
                k: [_to_dict(v) for v in vals]
                for k, vals in result["allocations"].items()
            },
            "errors": result["errors"],
        }
        return Response(out, status=status.HTTP_200_OK)


class InventoryAlertViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = InventoryAlert.objects.select_related("product", "nfe_item", "nota_fiscal").all()
    serializer_class = InventoryAlertSerializer
    filterset_fields = ["alert_type", "severity", "status"]
    http_method_names = ["get", "patch", "head", "options"]

    @action(detail=False, methods=["post"])
    def detect(self, request):
        """POST ?lookback_days=90 - run anomaly detection."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response({"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST)
        lookback_days = int(request.query_params.get("lookback_days", 90))
        result = run_anomaly_detection(tenant, lookback_days)
        return Response(result)


class ComparisonReportView(viewsets.ViewSet):
    """Comparison report and drilldown endpoints."""

    @action(detail=False, methods=["get"])
    def report(self, request):
        """GET ?start_date=...&end_date=...&strategies=wavg,fifo,lifo"""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response(
                {"error": "Tenant required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        strategies = request.query_params.get("strategies")
        if strategies:
            strategies = [s.strip() for s in strategies.split(",")]
        if not start_date or not end_date:
            return Response(
                {"error": "start_date and end_date required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from datetime import datetime
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        result = get_comparison_report(tenant, start_date, end_date, strategies)
        return Response(result)

    @action(detail=False, methods=["get"])
    def sku(self, request):
        """GET ?product_id=...&start_date=...&end_date=...&strategies=..."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response({"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST)
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response({"error": "product_id required"}, status=status.HTTP_400_BAD_REQUEST)
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        strategies = request.query_params.get("strategies")
        if strategies:
            strategies = [s.strip() for s in strategies.split(",")]
        if not start_date or not end_date:
            return Response(
                {"error": "start_date and end_date required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from datetime import datetime
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        result = get_sku_drilldown(tenant, int(product_id), start_date, end_date, strategies)
        return Response(result)

    @action(detail=False, methods=["get"])
    def movement(self, request):
        """GET ?movement_id=...&strategies=..."""
        tenant = getattr(request, "tenant", None)
        if not tenant or tenant == "all":
            return Response({"error": "Tenant required"}, status=status.HTTP_400_BAD_REQUEST)
        movement_id = request.query_params.get("movement_id")
        if not movement_id:
            return Response({"error": "movement_id required"}, status=status.HTTP_400_BAD_REQUEST)
        strategies = request.query_params.get("strategies")
        if strategies:
            strategies = [s.strip() for s in strategies.split(",")]
        result = get_movement_drilldown(tenant, int(movement_id), strategies)
        return Response(result)
