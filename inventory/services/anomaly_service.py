# -*- coding: utf-8 -*-
"""
Anomaly detection: pack-vs-unit pricing, price outliers.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count
from django.utils import timezone

from billing.models import NotaFiscalItem, ProductService
from inventory.models import InventoryAlert


def detect_pack_vs_unit(company, lookback_days=90):
    """
    Detect suspected pack-vs-unit pricing mistakes.
    Compares observed unit price against rolling median; flags large deviations.
    """
    since = timezone.now() - timedelta(days=lookback_days)
    items = NotaFiscalItem.objects.filter(
        company=company,
        nota_fiscal__data_emissao__gte=since,
    ).select_related("produto", "nota_fiscal")

    # Group by product (codigo_produto)
    from collections import defaultdict
    by_product = defaultdict(list)
    for item in items:
        key = item.codigo_produto or item.ean or ""
        if not key:
            continue
        by_product[key].append(item)

    alerts_created = 0
    for cod, product_items in by_product.items():
        if len(product_items) < 2:
            continue
        prices = [float(i.valor_unitario) for i in product_items if i.valor_unitario]
        if len(prices) < 2:
            continue
        import statistics
        try:
            median_price = statistics.median(prices)
        except statistics.StatisticsError:
            continue
        if median_price <= 0:
            continue

        for item in product_items:
            obs = float(item.valor_unitario or 0)
            if obs <= 0:
                continue
            deviation_ratio = obs / median_price
            if deviation_ratio > 5 or (deviation_ratio < 0.2 and deviation_ratio > 0):
                suspected = 12 if deviation_ratio > 5 else (1 / 12)
                if InventoryAlert.objects.filter(
                    company=company,
                    alert_type="pack_vs_unit",
                    nfe_item=item,
                    status="open",
                ).exists():
                    continue
                InventoryAlert.objects.create(
                    company=company,
                    alert_type="pack_vs_unit",
                    severity="warning",
                    product=item.produto,
                    nfe_item=item,
                    nota_fiscal=item.nota_fiscal,
                    title=f"Pack vs unit? Price {obs:.2f} vs median {median_price:.2f}",
                    description=f"Observed unit price {obs} deviates {deviation_ratio:.2f}x from median. Suspected conversion factor: {suspected}",
                    evidence={
                        "expected_unit_price": median_price,
                        "observed_unit_price": obs,
                        "deviation_ratio": deviation_ratio,
                        "suspected_conversion_factor": suspected,
                        "historical_reference_window": lookback_days,
                        "reference_items_count": len(product_items),
                    },
                    status="open",
                )
                alerts_created += 1

    return {"alerts_created": alerts_created}


def detect_price_outliers(company, lookback_days=90, z_threshold=3):
    """Z-score based price outlier detection per product."""
    since = timezone.now() - timedelta(days=lookback_days)
    items = NotaFiscalItem.objects.filter(
        company=company,
        nota_fiscal__data_emissao__gte=since,
    ).values("produto_id", "codigo_produto").annotate(
        avg_price=Avg("valor_unitario"),
        cnt=Count("id"),
    ).filter(cnt__gte=3)

    alerts_created = 0
    for row in items:
        if not row["produto_id"]:
            continue
        product_items = NotaFiscalItem.objects.filter(
            company=company,
            produto_id=row["produto_id"],
            nota_fiscal__data_emissao__gte=since,
        )
        prices = [float(i.valor_unitario) for i in product_items if i.valor_unitario]
        if len(prices) < 3:
            continue
        import statistics
        mean_p = statistics.mean(prices)
        try:
            stdev_p = statistics.stdev(prices)
        except statistics.StatisticsError:
            continue
        if stdev_p == 0:
            continue

        for item in product_items:
            obs = float(item.valor_unitario or 0)
            z = abs((obs - mean_p) / stdev_p) if stdev_p else 0
            if z >= z_threshold:
                if InventoryAlert.objects.filter(
                    company=company,
                    alert_type="price_outlier",
                    nfe_item=item,
                    status="open",
                ).exists():
                    continue
                InventoryAlert.objects.create(
                    company=company,
                    alert_type="price_outlier",
                    severity="info",
                    product=item.produto,
                    nfe_item=item,
                    nota_fiscal=item.nota_fiscal,
                    title=f"Price outlier: {obs:.2f} (z={z:.2f})",
                    description=f"Unit price {obs} is {z:.2f} std devs from mean {mean_p:.2f}",
                    evidence={
                        "observed_unit_price": obs,
                        "mean_price": mean_p,
                        "std_dev": stdev_p,
                        "z_score": z,
                        "historical_window": lookback_days,
                    },
                    status="open",
                )
                alerts_created += 1

    return {"alerts_created": alerts_created}


def run_anomaly_detection(company, lookback_days=90):
    """Run pack-vs-unit and price outlier detection."""
    r1 = detect_pack_vs_unit(company, lookback_days)
    r2 = detect_price_outliers(company, lookback_days)
    return {
        "pack_vs_unit": r1["alerts_created"],
        "price_outlier": r2["alerts_created"],
    }
