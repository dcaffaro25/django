"""KPI aggregations for the Bank Account Dashboard + Detail pages.

Three callables:

  * ``compute_dashboard_kpis(bank_account_qs, ...)`` -- org-wide
    totals + currency-grouped sums for the cross-account overview.
  * ``compute_account_kpis(bank_account, ...)`` -- per-account
    metrics for the Detail page header strip.
  * ``compute_monthly_flows(bank_account, months)`` -- 12-month
    inflow/outflow series for the Detail page bar chart.

Design notes:

  * Reconciliation rate is **count-based** in v1: matched bank txs /
    total bank txs in the window. Amount-weighted (apportioned) is
    available via ``BankTransactionSerializer._bank_tx_match_metrics``
    but iterating that across hundreds of rows is too expensive for
    a dashboard call. If operators need amount-weighted later, swap
    to a Subquery+Sum at the queryset level.
  * Inflow / outflow are **signed**: positive ``amount`` -> inflow,
    negative -> outflow. Returned as ABS strings for display.
  * "Stale" means: bank tx older than ``stale_days`` AND not in any
    reconciliation with status ``matched``/``approved``. Aligns
    with the operator-visible ``reconciliation_status`` annotation
    on ``BankTransactionViewSet``.
  * All amounts returned as strings (Decimal -> str) to preserve
    precision and survive JSON.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from django.db.models import (
    Case,
    Count,
    DecimalField,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone


def _today() -> dt.date:
    """Indirection so tests can monkey-patch the clock if needed."""
    return timezone.now().date()


def _zero() -> Decimal:
    return Decimal("0")


def compute_dashboard_kpis(
    *,
    bank_account_qs,
    stale_days: int = 30,
    recon_window_days: int = 30,
) -> Dict[str, Any]:
    """Org-wide aggregates across every (tenant-scoped) bank account.

    Returned shape:

        {
          "account_count": int,
          "active_account_count": int,
          "balance_by_currency": {"BRL": "12345.67", "USD": "..."},
          "stale_unreconciled_count": int,
          "reconciliation_rate_pct": int (0..100, count-basis),
          "inflow_mtd_by_currency":  {"BRL": "..."},
          "outflow_mtd_by_currency": {"BRL": "..."},
          "inflow_window_by_currency":  {"BRL": "..."},
          "outflow_window_by_currency": {"BRL": "..."},
          "currency_codes": ["BRL", "USD", ...],  # union, sorted
        }
    """
    from accounting.models import BankTransaction

    today = _today()
    month_start = today.replace(day=1)
    window_start = today - dt.timedelta(days=recon_window_days)
    stale_cutoff = today - dt.timedelta(days=stale_days)

    accounts = list(
        bank_account_qs.select_related("currency").only(
            "id", "currency_id", "balance",
        )
    )
    account_ids = [a.id for a in accounts]
    account_count = len(accounts)
    # ``BankAccount`` doesn't track ``is_active`` (only the parent
    # ``Bank`` does). Treat every BankAccount in the tenant scope as
    # "active" for v1 -- if soft-deletion is added later, the
    # default queryset will already filter dead rows out.
    active_account_count = account_count

    # Balance per currency: use BankAccount.get_current_balance() so we
    # respect the per-account anchor + post-anchor BankTransaction sum.
    # Slightly more expensive than reading ``balance`` directly but
    # the dashboard surface needs the live number.
    balance_by_currency: Dict[str, Decimal] = defaultdict(_zero)
    for a in accounts:
        code = getattr(a.currency, "code", None) or "?"
        try:
            balance_by_currency[code] += a.get_current_balance() or _zero()
        except Exception:
            # Defensive: any one account's bad data shouldn't black out
            # the whole dashboard.
            continue

    # The remaining metrics aggregate at the BankTransaction level. One
    # query per metric -- simpler than a single mega-query and reads
    # well at the diagnostic level.
    base_qs = BankTransaction.objects.filter(bank_account_id__in=account_ids)

    # Stale unreconciled count.
    stale_unreconciled_count = (
        base_qs.filter(date__lte=stale_cutoff)
        .exclude(reconciliations__status__in=["matched", "approved"])
        .distinct()  # exclude joins can multiply rows
        .count()
    )

    # Reconciliation rate (count-basis, recon_window_days back from today).
    window_qs = base_qs.filter(date__gte=window_start)
    total_in_window = window_qs.distinct().count()
    matched_in_window = (
        window_qs.filter(reconciliations__status__in=["matched", "approved"])
        .distinct()
        .count()
    )
    reconciliation_rate_pct = (
        int(round(matched_in_window * 100 / total_in_window))
        if total_in_window > 0 else 0
    )

    # Per-currency inflow / outflow aggregates.
    def _sum_by_currency(qs, sign: str) -> Dict[str, str]:
        if sign == "in":
            qs = qs.filter(amount__gt=0)
        else:
            qs = qs.filter(amount__lt=0)
        rows = (
            qs.values("currency__code")
            .annotate(total=Coalesce(Sum("amount"), Value(_zero(), output_field=DecimalField(max_digits=20, decimal_places=2))))
            .order_by()
        )
        return {
            (r["currency__code"] or "?"): str(abs(r["total"] or _zero()))
            for r in rows
        }

    mtd_qs = base_qs.filter(date__gte=month_start)
    inflow_mtd = _sum_by_currency(mtd_qs, "in")
    outflow_mtd = _sum_by_currency(mtd_qs, "out")
    inflow_window = _sum_by_currency(window_qs, "in")
    outflow_window = _sum_by_currency(window_qs, "out")

    currency_codes = sorted({
        *balance_by_currency.keys(),
        *inflow_mtd.keys(),
        *outflow_mtd.keys(),
        *inflow_window.keys(),
        *outflow_window.keys(),
    })

    return {
        "account_count": account_count,
        "active_account_count": active_account_count,
        "balance_by_currency": {
            code: str(amt) for code, amt in balance_by_currency.items()
        },
        "stale_unreconciled_count": stale_unreconciled_count,
        "reconciliation_rate_pct": reconciliation_rate_pct,
        "inflow_mtd_by_currency": inflow_mtd,
        "outflow_mtd_by_currency": outflow_mtd,
        "inflow_window_by_currency": inflow_window,
        "outflow_window_by_currency": outflow_window,
        "currency_codes": currency_codes,
        "stale_days": stale_days,
        "recon_window_days": recon_window_days,
    }


def compute_account_kpis(
    *,
    bank_account,
    stale_days: int = 30,
    recon_window_days: int = 30,
) -> Dict[str, Any]:
    """Per-account metrics for the Detail page header strip.

    Same recon-window / stale semantics as ``compute_dashboard_kpis``
    but scoped to one ``BankAccount``.
    """
    from accounting.models import BankTransaction

    today = _today()
    month_start = today.replace(day=1)
    window_start = today - dt.timedelta(days=recon_window_days)
    stale_cutoff = today - dt.timedelta(days=stale_days)

    base_qs = BankTransaction.objects.filter(bank_account=bank_account)

    transaction_count = base_qs.count()
    last_transaction_at = (
        base_qs.order_by("-date").values_list("date", flat=True).first()
    )

    stale_unreconciled_count = (
        base_qs.filter(date__lte=stale_cutoff)
        .exclude(reconciliations__status__in=["matched", "approved"])
        .distinct()
        .count()
    )

    window_qs = base_qs.filter(date__gte=window_start)
    total_in_window = window_qs.distinct().count()
    matched_in_window = (
        window_qs.filter(reconciliations__status__in=["matched", "approved"])
        .distinct()
        .count()
    )
    reconciliation_rate_pct = (
        int(round(matched_in_window * 100 / total_in_window))
        if total_in_window > 0 else 0
    )

    # Inflow / outflow (single currency for one account).
    def _sum_signed(qs, gt: bool) -> Decimal:
        rows = qs.aggregate(
            total=Coalesce(
                Sum("amount", filter=Q(amount__gt=0) if gt else Q(amount__lt=0)),
                Value(_zero(), output_field=DecimalField(max_digits=20, decimal_places=2)),
            )
        )
        return abs(rows["total"] or _zero())

    mtd_qs = base_qs.filter(date__gte=month_start)
    inflow_mtd = _sum_signed(mtd_qs, gt=True)
    outflow_mtd = _sum_signed(mtd_qs, gt=False)
    inflow_window = _sum_signed(window_qs, gt=True)
    outflow_window = _sum_signed(window_qs, gt=False)

    # Last reconciliation timestamp -- most-recent ``created_at``
    # across recs that touch this account.
    from accounting.models import Reconciliation
    last_reconciliation_at = (
        Reconciliation.objects.filter(bank_transactions__bank_account=bank_account)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )

    try:
        current_balance = bank_account.get_current_balance() or _zero()
    except Exception:
        current_balance = _zero()

    return {
        "id": bank_account.id,
        "name": bank_account.name,
        "currency_code": getattr(getattr(bank_account, "currency", None), "code", None),
        "current_balance": str(current_balance),
        "transaction_count": transaction_count,
        "last_transaction_at": last_transaction_at.isoformat() if last_transaction_at else None,
        "last_reconciliation_at": last_reconciliation_at.isoformat() if last_reconciliation_at else None,
        "stale_unreconciled_count": stale_unreconciled_count,
        "reconciliation_rate_pct": reconciliation_rate_pct,
        "inflow_mtd": str(inflow_mtd),
        "outflow_mtd": str(outflow_mtd),
        "inflow_window": str(inflow_window),
        "outflow_window": str(outflow_window),
        "stale_days": stale_days,
        "recon_window_days": recon_window_days,
    }


def compute_monthly_flows(
    *,
    bank_account,
    months: int = 12,
) -> List[Dict[str, str]]:
    """12-month inflow/outflow series ordered oldest -> newest.

    Months with no activity still emit zero rows so the frontend
    bar chart can render a continuous x-axis without filling gaps
    in JS. ``months`` is bounded by the caller (viewset clamps to
    1..60).
    """
    from accounting.models import BankTransaction

    today = _today()
    # First day of (today - months + 1) months ago, to cover the
    # full window incl. the current month.
    year = today.year
    month = today.month - (months - 1)
    while month <= 0:
        month += 12
        year -= 1
    window_start = dt.date(year, month, 1)

    qs = (
        BankTransaction.objects.filter(
            bank_account=bank_account, date__gte=window_start,
        )
        .annotate(m=TruncMonth("date"))
        .values("m")
        .annotate(
            inflow=Coalesce(
                Sum("amount", filter=Q(amount__gt=0)),
                Value(_zero(), output_field=DecimalField(max_digits=20, decimal_places=2)),
            ),
            outflow=Coalesce(
                Sum("amount", filter=Q(amount__lt=0)),
                Value(_zero(), output_field=DecimalField(max_digits=20, decimal_places=2)),
            ),
        )
        .order_by("m")
    )
    by_month: Dict[str, Dict[str, Decimal]] = {
        r["m"].strftime("%Y-%m"): {
            "inflow": r["inflow"] or _zero(),
            "outflow": abs(r["outflow"] or _zero()),
        }
        for r in qs
    }

    # Fill gaps so the chart x-axis is continuous.
    result: List[Dict[str, str]] = []
    cursor = window_start
    while cursor <= today.replace(day=1):
        key = cursor.strftime("%Y-%m")
        bucket = by_month.get(key, {"inflow": _zero(), "outflow": _zero()})
        result.append({
            "month": key,
            "inflow": str(bucket["inflow"]),
            "outflow": str(bucket["outflow"]),
        })
        # Advance one month.
        if cursor.month == 12:
            cursor = dt.date(cursor.year + 1, 1, 1)
        else:
            cursor = dt.date(cursor.year, cursor.month + 1, 1)
    return result
