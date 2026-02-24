# -*- coding: utf-8 -*-
"""
Inventory app URLs. Mounted under /{tenant_id}/ in main urls.py.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"warehouses", views.WarehouseViewSet, basename="warehouse")
router.register(r"uom", views.UnitOfMeasureViewSet, basename="uom")
router.register(r"uom-conversions", views.UoMConversionViewSet, basename="uom-conversion")
router.register(r"movements", views.StockMovementViewSet, basename="movement")
router.register(r"balances", views.InventoryBalanceViewSet, basename="balance")
router.register(r"alerts", views.InventoryAlertViewSet, basename="alert")
router.register(r"costing", views.CostingComputeView, basename="costing")
router.register(r"comparison", views.ComparisonReportView, basename="comparison")

urlpatterns = [
    path("api/inventory/", include(router.urls)),
]
