# -*- coding: utf-8 -*-
"""
Days Sales Outstanding (DSO) report.

Standard accounting receivables KPI:

    DSO = (Outstanding AR at period end / Total Credit Sales in period)
          * days_in_period

Lower is better — it's the average number of days the company waits
to collect after a sale. Companies typically benchmark DSO against
their stated payment terms (Brazil: ~28-45d for standard B2B).

Per-tenant DSO is the headline number; per-partner DSO drives the
"who's making us wait" drill-down. Aging buckets at the end of the
period (0-30 / 31-60 / 61-90 / 91+) supplement DSO with the
*shape* of the AR -- two tenants can have the same DSO but very
different aging distributions.

Source: ``billing.Invoice`` filtered by ``invoice_type='sale'``.
Outstanding = invoices in status ``issued`` or ``partially_paid``
(``draft`` is pre-billing; ``paid`` and ``canceled`` are out).
``partially_paid`` is treated as fully outstanding for the V1
report — the actual paid portion is tracked separately by the
JE-matching pipeline and isn't denormalized on Invoice today. A
follow-up that joins payment-side JEs to subtract the paid portion
would tighten this; the rough form is still standard practice
across DSO tooling.

Aging anchor: ``invoice_date`` is the conventional basis ("days
since invoiced"). We also report ``days_past_due`` (today -
``due_date``) so operators can separate "open but on-time" from
"overdue".
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date as _date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from django.db.models import Q, Sum, Count

from billing.models import BusinessPartner, Invoice

logger = logging.getLogger(__name__)


_OPEN_AR_STATUSES = ("issued", "partially_paid")


@dataclass
class AgingBucket:
    label: str
    days_min: int
    days_max: Optional[int]  # None = open-ended
    count: int = 0
    amount: Decimal = Decimal("0")

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "days_min": self.days_min,
            "days_max": self.days_max,
            "count": self.count,
            "amount": str(self.amount),
        }


def _new_buckets() -> List[AgingBucket]:
    return [
        AgingBucket("0-30", 0, 30),
        AgingBucket("31-60", 31, 60),
        AgingBucket("61-90", 61, 90),
        AgingBucket("91+", 91, None),
    ]


def _bucket_for_age(buckets: List[AgingBucket], age_days: int) -> AgingBucket:
    for b in buckets:
        if b.days_max is None:
            if age_days >= b.days_min:
                return b
        elif b.days_min <= age_days <= b.days_max:
            return b
    # 91+ catches everything; should never reach here.
    return buckets[-1]


def compute_dso(
    company,
    *,
    date_from: _date,
    date_to: _date,
    partner_id: Optional[int] = None,
    top_n_partners: int = 10,
) -> dict:
    """Compute DSO + aging for ``[date_from, date_to]``.

    Args:
        company: tenant.
        date_from / date_to: inclusive sales window for the
            denominator. The AR snapshot is taken at ``date_to``.
        partner_id: optional scope to one partner. When set, the
            ``per_partner`` block is skipped (single-partner mode).
        top_n_partners: cap on the per-partner block.

    Returns:
        {
          period: {date_from, date_to, days},
          totals: {sales, ar_open, dso_days, days_in_period},
          aging: [{label, count, amount}, ...],
          per_partner: [
            {
              partner_id, partner_name, partner_identifier,
              sales, ar_open, dso_days, weighted_avg_age_days
            },
            ...
          ],  // sorted by ar_open desc, capped at top_n_partners
          notes: str
        }

    Edge cases:
        - Zero credit sales in the period → ``dso_days`` is None
          (formula divides by zero). Aging is still meaningful.
        - Zero AR at period end → ``dso_days`` = 0.
    """
    if date_from > date_to:
        raise ValueError("date_from must be <= date_to")

    days_in_period = (date_to - date_from).days + 1

    # ---- Sales: invoices issued in the window ----
    sales_qs = Invoice.objects.filter(
        company=company,
        invoice_type="sale",
        invoice_date__gte=date_from,
        invoice_date__lte=date_to,
    ).exclude(status="canceled")
    if partner_id is not None:
        sales_qs = sales_qs.filter(partner_id=partner_id)

    # Per-partner sales aggregation (used by both totals and
    # per_partner block).
    sales_by_partner = defaultdict(lambda: Decimal("0"))
    sales_total = Decimal("0")
    for r in sales_qs.values("partner_id").annotate(s=Sum("total_amount")):
        amt = Decimal(r["s"] or 0)
        sales_by_partner[r["partner_id"]] = amt
        sales_total += amt

    # ---- AR snapshot at date_to: invoices issued ON OR BEFORE
    #       date_to that are still open at request time. The "still
    #       open" check is the live status — the model doesn't carry
    #       a per-date status history, so DSO computed for past
    #       windows reflects current AR shape, not historical. Worth
    #       calling out in the response notes.
    ar_qs = Invoice.objects.filter(
        company=company,
        invoice_type="sale",
        invoice_date__lte=date_to,
        status__in=_OPEN_AR_STATUSES,
    )
    if partner_id is not None:
        ar_qs = ar_qs.filter(partner_id=partner_id)

    ar_rows = list(
        ar_qs.values(
            "id", "partner_id", "total_amount", "invoice_date", "due_date",
        )
    )
    ar_total = Decimal("0")
    ar_by_partner = defaultdict(lambda: {"amount": Decimal("0"), "weighted_age": Decimal("0"), "count": 0})
    buckets = _new_buckets()
    today = _date.today()  # for live aging
    for r in ar_rows:
        amt = Decimal(r["total_amount"] or 0)
        if amt == 0:
            continue
        ar_total += amt
        # Aging anchored on invoice_date — conventional DSO basis.
        age = (today - r["invoice_date"]).days if r["invoice_date"] else 0
        b = _bucket_for_age(buckets, max(0, age))
        b.count += 1
        b.amount += amt
        # Per-partner accumulation
        pp = ar_by_partner[r["partner_id"]]
        pp["amount"] += amt
        pp["weighted_age"] += amt * Decimal(age)
        pp["count"] += 1

    # ---- DSO totals ----
    dso_days: Optional[Decimal] = None
    if sales_total > 0:
        dso_days = (ar_total / sales_total * Decimal(days_in_period)).quantize(Decimal("0.01"))
    elif ar_total == 0:
        dso_days = Decimal("0.00")

    # ---- Per-partner DSO ----
    per_partner: List[dict] = []
    if partner_id is None:
        # All partners that appear in either sales or AR
        partner_ids = set(sales_by_partner.keys()) | set(ar_by_partner.keys())
        partner_meta: Dict[int, dict] = {
            p.id: {"name": p.name, "identifier": p.identifier or ""}
            for p in BusinessPartner.objects.filter(
                company=company, id__in=list(partner_ids),
            ).only("id", "name", "identifier")
        }
        for pid in partner_ids:
            sales_p = sales_by_partner.get(pid, Decimal("0"))
            ar_p_data = ar_by_partner.get(pid, {"amount": Decimal("0"), "weighted_age": Decimal("0"), "count": 0})
            ar_p = ar_p_data["amount"]
            if sales_p > 0:
                dso_p = (ar_p / sales_p * Decimal(days_in_period)).quantize(Decimal("0.01"))
            elif ar_p == 0:
                dso_p = Decimal("0.00")
            else:
                # Has AR but no sales in window — DSO is meaningless;
                # report as None so caller can render '—'.
                dso_p = None
            avg_age = None
            if ar_p > 0 and ar_p_data["count"] > 0:
                avg_age = (ar_p_data["weighted_age"] / ar_p).quantize(Decimal("0.01"))
            meta = partner_meta.get(pid, {})
            per_partner.append({
                "partner_id": pid,
                "partner_name": meta.get("name", f"BP#{pid}"),
                "partner_identifier": meta.get("identifier", ""),
                "sales": str(sales_p),
                "ar_open": str(ar_p),
                "ar_invoice_count": ar_p_data["count"],
                "dso_days": str(dso_p) if dso_p is not None else None,
                "weighted_avg_age_days": str(avg_age) if avg_age is not None else None,
            })
        # Sort by AR desc (the "who do we need to chase" lens), then
        # by DSO desc (slowest payers within similar AR).
        per_partner.sort(
            key=lambda r: (
                Decimal(r["ar_open"]),
                Decimal(r["dso_days"]) if r["dso_days"] else Decimal("0"),
            ),
            reverse=True,
        )
        per_partner = per_partner[:top_n_partners]

    return {
        "period": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "days": days_in_period,
        },
        "totals": {
            "sales": str(sales_total),
            "ar_open": str(ar_total),
            "dso_days": str(dso_days) if dso_days is not None else None,
            "days_in_period": days_in_period,
            "open_invoice_count": len([r for r in ar_rows if Decimal(r["total_amount"] or 0) > 0]),
        },
        "aging": [b.to_dict() for b in buckets],
        "per_partner": per_partner,
        "notes": (
            "AR snapshot is taken at the *current* invoice status "
            "(model doesn't carry per-date status history), so DSO "
            "for past windows reflects today's open AR, not what "
            "was open at ``date_to``. ``partially_paid`` invoices "
            "count their full ``total_amount`` toward AR -- payment "
            "tracking by JE matching isn't denormalized on Invoice. "
            "Aging is anchored on ``invoice_date`` (conventional "
            "DSO basis); separate ``days_past_due`` is exposed by "
            "the Tx-status endpoint when needed."
        ),
    }
