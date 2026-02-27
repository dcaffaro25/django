# -*- coding: utf-8 -*-
"""
Posting service: strategy-aware accounting entries. Idempotent via AccountingImpact.
"""
from decimal import Decimal

from django.db import transaction

from accounting.models import Transaction, JournalEntry, Account
from accounting.services.transaction_service import post_transaction, validate_transaction_balanced
from multitenancy.models import Entity

from inventory.models import (
    CogsAllocation,
    AccountingImpact,
    TenantCostingConfig,
)
from billing.models import ProductService


def get_accounts_for_product(product, config):
    """
    Resolve inventory, COGS, and adjustment accounts for a product.
    Uses product-level account fields when set, otherwise falls back to TenantCostingConfig.
    Returns (inventory_account, cogs_account, adjustment_account).
    """
    return (
        product.inventory_account or config.inventory_account,
        product.cogs_account or config.cogs_account,
        product.adjustment_account or config.adjustment_account,
    )


def _get_default_entity(company):
    """Get first entity for company, or None."""
    return Entity.objects.filter(company=company).first()


def _get_default_currency(company):
    """Get default currency (BRL or first)."""
    from accounting.models import Currency
    return Currency.objects.filter(code="BRL").first() or Currency.objects.first()


def _get_config(company):
    """Get TenantCostingConfig or create default."""
    config, _ = TenantCostingConfig.objects.get_or_create(
        company=company,
        defaults={
            "primary_strategy": "weighted_average",
            "enabled_strategies": ["weighted_average", "fifo", "lifo"],
        },
    )
    return config


def _idempotency_key_exists(company, strategy, posting_type, source_document_type, source_document_id):
    """Check if we already posted (idempotent)."""
    qs = AccountingImpact.objects.filter(
        company=company,
        strategy=strategy,
        posting_type=posting_type,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
    )
    return qs.exists()


def post_cogs_entry(company, cogs_allocation, strategy):
    """
    Post Dr COGS / Cr Inventory for a single COGS allocation.
    Idempotent: skips if AccountingImpact already exists.
    """
    if _idempotency_key_exists(
        company, strategy, "cogs", "stock_movement", cogs_allocation.outbound_movement_id
    ):
        return None, "Already posted"

    config = _get_config(company)
    product = cogs_allocation.product
    inventory_account, cogs_account, _ = get_accounts_for_product(product, config)
    if not cogs_account or not inventory_account:
        return None, "COGS or Inventory account not configured"

    entity = _get_default_entity(company)
    currency = _get_default_currency(company)
    if not entity or not currency:
        return None, "Entity or Currency not configured"

    mov = cogs_allocation.outbound_movement
    amount = cogs_allocation.total_cogs
    description = f"COGS {strategy} - {mov.reference} (mov #{mov.id})"

    with transaction.atomic():
        txn = Transaction.objects.create(
            company=company,
            date=mov.movement_date.date() if hasattr(mov.movement_date, "date") else mov.movement_date,
            entity=entity,
            description=description,
            amount=amount,
            currency=currency,
            state="pending",
        )
        JournalEntry.objects.create(
            company=company,
            transaction=txn,
            account=cogs_account,
            debit_amount=amount,
            credit_amount=None,
            state="pending",
            date=txn.date,
        )
        JournalEntry.objects.create(
            company=company,
            transaction=txn,
            account=inventory_account,
            debit_amount=None,
            credit_amount=amount,
            state="pending",
            date=txn.date,
        )
        if validate_transaction_balanced(txn):
            post_transaction(txn)
        else:
            raise ValueError("Transaction not balanced")

        AccountingImpact.objects.create(
            company=company,
            strategy=strategy,
            posting_type="cogs",
            source_document_type="stock_movement",
            source_document_id=mov.id,
            transaction=txn,
            accounts_detail=[
                {"account_id": cogs_account.id, "debit": float(amount), "credit": 0},
                {"account_id": inventory_account.id, "debit": 0, "credit": float(amount)},
            ],
            total_debit=amount,
            total_credit=amount,
        )
    return txn, None


def post_period_close_adjustments(company, period_end_date, strategies=None):
    """
    Post period-close valuation adjustments per strategy.
    Option 1: Compare ending inventory value to primary; post adjustment for non-primary strategies.
    For now, creates a placeholder - full logic would compute delta vs primary and post.
    """
    config = _get_config(company)
    if strategies is None:
        strategies = config.enabled_strategies or ["weighted_average", "fifo", "lifo"]
    primary = config.primary_strategy
    source_doc_id = int(period_end_date.strftime("%Y%m%d"))

    results = []
    for strategy in strategies:
        if _idempotency_key_exists(
            company, strategy, "period_close_adjustment", "period_close", source_doc_id
        ):
            results.append({"strategy": strategy, "status": "skipped", "reason": "Already posted"})
            continue
        # Full implementation would:
        # 1. Get valuation snapshots for primary and this strategy
        # 2. Compute delta
        # 3. Post adjusting entry
        results.append({
            "strategy": strategy,
            "status": "not_implemented",
            "reason": "Period close adjustment logic to be implemented",
        })
    return results
