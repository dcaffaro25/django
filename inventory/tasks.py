# -*- coding: utf-8 -*-
"""
Celery tasks for inventory: NF ingestion, costing recompute, anomaly detection.
"""
from datetime import date, datetime

from celery import shared_task
from django.utils import timezone

from multitenancy.models import Company


@shared_task(bind=True)
def ingest_nf_movements_task(self, company_id, nota_fiscal_ids=None):
    """
    Ingest NF-e items into stock movements for a company.
    If nota_fiscal_ids is None, processes all NFs for the company.
    """
    from inventory.services.movement_service import ingest_nf_to_movements

    company = Company.objects.filter(id=company_id).first()
    if not company:
        return {"error": "Company not found", "company_id": company_id}

    result = ingest_nf_to_movements(
        company=company,
        nota_fiscal_ids=nota_fiscal_ids,
    )
    return result


@shared_task(bind=True)
def rebuild_and_snapshot_task(
    self,
    company_id,
    strategy_keys=None,
    start_date=None,
    end_date=None,
    product_ids=None,
    warehouse_ids=None,
):
    """Run costing engine and persist valuation snapshots + COGS allocations."""
    from inventory.services.costing_engine import compute_for_strategies

    company = Company.objects.filter(id=company_id).first()
    if not company:
        return {"error": "Company not found", "company_id": company_id}

    if start_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if end_date:
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    result = compute_for_strategies(
        company=company,
        strategy_keys=strategy_keys,
        start_date=start_date,
        end_date=end_date,
        product_ids=product_ids,
        warehouse_ids=warehouse_ids,
    )
    return {
        "valuations_count": {k: len(v) for k, v in result["valuations"].items()},
        "allocations_count": {k: len(v) for k, v in result["allocations"].items()},
        "errors": result["errors"],
    }


@shared_task(bind=True)
def period_close_task(self, company_id, period_end_date_str):
    """Run period close: snapshots + adjusting entries (placeholder)."""
    from inventory.services.costing_engine import compute_for_strategies
    from inventory.services.posting_service import post_period_close_adjustments

    company = Company.objects.filter(id=company_id).first()
    if not company:
        return {"error": "Company not found"}

    period_end = datetime.strptime(period_end_date_str, "%Y-%m-%d").date()
    compute_for_strategies(company=company, end_date=period_end)
    adjustments = post_period_close_adjustments(company, period_end)
    return {"adjustments": adjustments}


@shared_task(bind=True)
def detect_anomalies_task(self, company_id, lookback_days=90):
    """Run anomaly detection (pack-vs-unit, price outliers)."""
    from inventory.services.anomaly_service import run_anomaly_detection

    company = Company.objects.filter(id=company_id).first()
    if not company:
        return {"error": "Company not found"}

    return run_anomaly_detection(company=company, lookback_days=lookback_days)
