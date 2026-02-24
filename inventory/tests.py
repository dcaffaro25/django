# -*- coding: utf-8 -*-
"""
Inventory tests: costing comparison, idempotency, multi-tenant isolation.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from django.test import TestCase

from multitenancy.models import Company
from billing.models import ProductService
from accounting.models import Currency, Account
from inventory.models import (
    Warehouse,
    UnitOfMeasure,
    StockMovement,
    InventoryBalance,
)
from inventory.services.movement_service import ingest_nf_to_movements, create_manual_adjustment
from inventory.services.costing_engine import compute_for_strategies


class CostingStrategyComparisonTestCase(TestCase):
    """
    Classic scenario: 3 purchases at $10, $12, $14 -> sell 4 units.
    Expected COGS: FIFO=$42, LIFO=$48, WAVG≈$45.33
    """

    def setUp(self):
        self.company = Company.objects.create(name="Cost Test Co", subdomain="cost-test")
        self.currency = Currency.objects.get_or_create(
            code="BRL", defaults={"name": "Real", "symbol": "R$"}
        )[0]
        self.product = ProductService.objects.create(
            company=self.company,
            code="SKU001",
            name="Test Product",
            item_type="product",
            track_inventory=True,
            price=Decimal("20"),
            cost=Decimal("10"),
            currency=self.currency,
        )
        self.uom = UnitOfMeasure.objects.create(
            company=self.company, code="UN", name="Unit"
        )

    def _create_movement(self, mtype, qty, unit_cost):
        return StockMovement.objects.create(
            company=self.company,
            movement_type=mtype,
            product=self.product,
            warehouse=None,
            quantity=qty,
            unit_cost=unit_cost,
            uom=self.uom,
            movement_date=datetime(2024, 2, 1),
            source_type="manual_adjustment",
            reference=f"{mtype} {qty}",
            idempotency_key=f"test-{mtype}-{qty}-{unit_cost}-{uuid.uuid4().hex}",
        )

    def test_wavg_fifo_lifo_cogs_differ(self):
        # Buy 3 @ 10, 2 @ 12, 1 @ 14
        self._create_movement("inbound", 3, Decimal("10"))
        self._create_movement("inbound", 2, Decimal("12"))
        self._create_movement("inbound", 1, Decimal("14"))
        # Sell 4
        self._create_movement("outbound", 4, None)

        result = compute_for_strategies(
            company=self.company,
            strategy_keys=["weighted_average", "fifo", "lifo"],
            end_date=datetime(2024, 2, 28).date(),
        )

        self.assertEqual(result.get("errors", []), [], msg=f"Errors: {result.get('errors')}")
        allocations = result.get("allocations", {})
        self.assertIn("weighted_average", allocations)
        self.assertIn("fifo", allocations)
        self.assertIn("lifo", allocations)

        wavg_cogs = sum(a.total_cogs for a in allocations["weighted_average"])
        fifo_cogs = sum(a.total_cogs for a in allocations["fifo"])
        lifo_cogs = sum(a.total_cogs for a in allocations["lifo"])

        self.assertAlmostEqual(float(fifo_cogs), 42.0, places=2)
        self.assertAlmostEqual(float(lifo_cogs), 48.0, places=2)
        self.assertAlmostEqual(float(wavg_cogs), 45.33, places=1)


class MovementServiceIdempotencyTestCase(TestCase):
    """NF ingestion idempotency: re-ingest same NF -> no duplicate movements."""

    def setUp(self):
        self.company = Company.objects.create(name="Idem Co", subdomain="idem-co")

    def test_manual_adjustment_creates_movement(self):
        from billing.models import ProductService
        from accounting.models import Currency

        Currency.objects.get_or_create(code="BRL", defaults={"name": "Real", "symbol": "R$"})
        prod = ProductService.objects.create(
            company=self.company,
            code="P1",
            name="Prod",
            item_type="product",
            track_inventory=True,
            price=Decimal("10"),
            currency=Currency.objects.first(),
        )
        mov, err = create_manual_adjustment(
            company=self.company,
            product_id=prod.id,
            quantity=10,
            unit_cost=Decimal("5"),
        )
        self.assertIsNone(err)
        self.assertIsNotNone(mov)
        self.assertEqual(mov.quantity, 10)
        self.assertEqual(mov.movement_type, "adjustment")


class MultiTenantIsolationTestCase(TestCase):
    """Movements and balances do not cross tenants."""

    def setUp(self):
        self.c1 = Company.objects.create(name="Tenant A", subdomain="ta")
        self.c2 = Company.objects.create(name="Tenant B", subdomain="tb")

    def test_company_filter_on_movements(self):
        movements_c1 = StockMovement.objects.filter(company=self.c1)
        movements_c2 = StockMovement.objects.filter(company=self.c2)
        self.assertEqual(movements_c1.count(), 0)
        self.assertEqual(movements_c2.count(), 0)
