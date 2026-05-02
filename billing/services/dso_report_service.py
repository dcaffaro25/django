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
from billing.services.invoice_payment_evidence import (
    EVIDENCE_CASH_MATCHED_FULL, EVIDENCE_CASH_MATCHED_PARTIAL,
    EVIDENCE_LINKED_NO_RECON, EVIDENCE_NF_LINKED_NO_TX,
    EVIDENCE_UNLINKED, classify_many,
)

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

    ar_invoices = list(
        ar_qs.only("id", "partner_id", "total_amount", "invoice_date", "due_date")
    )
    # Payment-evidence walk: which AR invoices already have linked
    # reconciled Tx? Operators see "we say open but cash matched" so
    # the headline DSO doesn't mislead while ``Invoice.status`` is
    # being kept current by the auto-update hook + backfill.
    evidence_by_inv = classify_many(ar_invoices)

    ar_total = Decimal("0")
    # Per-partner aggregation expanded with the four evidence buckets
    # so the per-partner table can show "of this partner's R$ X open,
    # R$ Y already shows cash evidence". Keys mirror EVIDENCE_*.
    ar_by_partner = defaultdict(
        lambda: {
            "amount": Decimal("0"),
            "weighted_age": Decimal("0"),
            "count": 0,
            "amount_cash_matched_full": Decimal("0"),
            "amount_cash_matched_partial": Decimal("0"),
            "amount_linked_no_recon": Decimal("0"),
            "amount_nf_linked_no_tx": Decimal("0"),
            "amount_unlinked": Decimal("0"),
            "count_cash_matched_full": 0,
        }
    )
    # Tenant-wide evidence breakdown.
    by_evidence_amount = {k: Decimal("0") for k in (
        EVIDENCE_CASH_MATCHED_FULL, EVIDENCE_CASH_MATCHED_PARTIAL,
        EVIDENCE_LINKED_NO_RECON, EVIDENCE_NF_LINKED_NO_TX,
        EVIDENCE_UNLINKED,
    )}
    by_evidence_count = {k: 0 for k in by_evidence_amount}

    buckets = _new_buckets()
    today = _date.today()  # for live aging
    for inv in ar_invoices:
        amt = Decimal(inv.total_amount or 0)
        if amt == 0:
            continue
        ar_total += amt
        age = (today - inv.invoice_date).days if inv.invoice_date else 0
        b = _bucket_for_age(buckets, max(0, age))
        b.count += 1
        b.amount += amt
        pp = ar_by_partner[inv.partner_id]
        pp["amount"] += amt
        pp["weighted_age"] += amt * Decimal(age)
        pp["count"] += 1
        ev = evidence_by_inv.get(inv.id)
        if ev is not None:
            by_evidence_amount[ev.status] += amt
            by_evidence_count[ev.status] += 1
            pp[f"amount_{ev.status}"] += amt
            if ev.status == EVIDENCE_CASH_MATCHED_FULL:
                pp["count_cash_matched_full"] += 1

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
            if ar_p > 0 and ar_p_data.get("count", 0) > 0:
                avg_age = (ar_p_data["weighted_age"] / ar_p).quantize(Decimal("0.01"))
            meta = partner_meta.get(pid, {})
            per_partner.append({
                "partner_id": pid,
                "partner_name": meta.get("name", f"BP#{pid}"),
                "partner_identifier": meta.get("identifier", ""),
                "sales": str(sales_p),
                "ar_open": str(ar_p),
                "ar_invoice_count": ar_p_data.get("count", 0),
                "dso_days": str(dso_p) if dso_p is not None else None,
                "weighted_avg_age_days": str(avg_age) if avg_age is not None else None,
                # Payment-evidence breakdown for the per-partner table.
                # ``ar_likely_paid`` = portion the auto-promotion hook
                # / backfill would mark as paid right now.
                "ar_likely_paid": str(ar_p_data.get("amount_cash_matched_full", Decimal("0"))),
                "ar_partial_evidence": str(ar_p_data.get("amount_cash_matched_partial", Decimal("0"))),
                "ar_no_evidence": str(
                    ar_p_data.get("amount_linked_no_recon", Decimal("0"))
                    + ar_p_data.get("amount_nf_linked_no_tx", Decimal("0"))
                    + ar_p_data.get("amount_unlinked", Decimal("0"))
                ),
                "ar_likely_paid_count": ar_p_data.get("count_cash_matched_full", 0),
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

    # ---- Adjusted DSO: subtract invoices with cash_matched_full
    #      evidence from open AR (those would be promoted to ``paid``
    #      by the backfill / auto-update hook). Lets operators see
    #      "real" DSO once the status-update plumbing catches up.
    likely_paid_amount = by_evidence_amount[EVIDENCE_CASH_MATCHED_FULL]
    ar_adjusted = ar_total - likely_paid_amount
    dso_adjusted: Optional[Decimal] = None
    if sales_total > 0:
        dso_adjusted = (ar_adjusted / sales_total * Decimal(days_in_period)).quantize(Decimal("0.01"))
    elif ar_adjusted == 0:
        dso_adjusted = Decimal("0.00")

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
            "open_invoice_count": len([
                inv for inv in ar_invoices if Decimal(inv.total_amount or 0) > 0
            ]),
            # Adjusted view that excludes invoices the backfill /
            # hook would mark as paid right now.
            "ar_adjusted": str(ar_adjusted),
            "dso_days_adjusted": str(dso_adjusted) if dso_adjusted is not None else None,
            "ar_likely_paid_amount": str(likely_paid_amount),
            "ar_likely_paid_count": by_evidence_count[EVIDENCE_CASH_MATCHED_FULL],
        },
        "aging": [b.to_dict() for b in buckets],
        "payment_evidence": {
            # Mutually exclusive buckets (each invoice in exactly one).
            # Use these to drive a stacked bar / donut on the dashboard.
            "cash_matched_full": {
                "count": by_evidence_count[EVIDENCE_CASH_MATCHED_FULL],
                "amount": str(by_evidence_amount[EVIDENCE_CASH_MATCHED_FULL]),
            },
            "cash_matched_partial": {
                "count": by_evidence_count[EVIDENCE_CASH_MATCHED_PARTIAL],
                "amount": str(by_evidence_amount[EVIDENCE_CASH_MATCHED_PARTIAL]),
            },
            "linked_no_recon": {
                "count": by_evidence_count[EVIDENCE_LINKED_NO_RECON],
                "amount": str(by_evidence_amount[EVIDENCE_LINKED_NO_RECON]),
            },
            "nf_linked_no_tx": {
                "count": by_evidence_count[EVIDENCE_NF_LINKED_NO_TX],
                "amount": str(by_evidence_amount[EVIDENCE_NF_LINKED_NO_TX]),
            },
            "unlinked": {
                "count": by_evidence_count[EVIDENCE_UNLINKED],
                "amount": str(by_evidence_amount[EVIDENCE_UNLINKED]),
            },
        },
        "per_partner": per_partner,
        "notes": (
            "AR snapshot is taken at the *current* invoice status "
            "(model doesn't carry per-date status history), so DSO "
            "for past windows reflects today's open AR, not what "
            "was open at ``date_to``. ``partially_paid`` invoices "
            "count their full ``total_amount`` toward AR -- payment "
            "tracking by JE matching isn't denormalized on Invoice. "
            "Aging is anchored on ``invoice_date`` (conventional "
            "DSO basis). ``payment_evidence`` shows how much of "
            "open AR already has matched-and-reconciled cash on "
            "the bank side -- those invoices would be promoted to "
            "``paid`` by the backfill / auto-update hook; "
            "``dso_days_adjusted`` is the headline DSO with that "
            "amount subtracted from AR."
        ),
    }
