# -*- coding: utf-8 -*-
"""
Consolidated transaction-status service — one place that combines the
pre-computed flags on ``accounting.Transaction`` into a single
classified row + portfolio-level aggregates.

The Transaction model already carries the raw signals:
    is_balanced, is_reconciled, is_posted, state,
    reconciliation_rate (0..100), days_outstanding, due_date,
    total_amount_discrepancy, avg_amount_discrepancy

What's missing is a coherent surface for the operator: a "status"
phrase ("partially reconciled, 12 days overdue") instead of having
to read seven booleans, plus aggregate bucket counts for a dashboard.

Four orthogonal dimensions per Tx, computed here:

* ``recon_status`` — pure reconciliation state, ignoring posting:
    - ``unbalanced`` : is_balanced=False (debit ≠ credit; data error)
    - ``reconciled`` : is_reconciled=True (every JE is matched)
    - ``partial``    : 0 < reconciliation_rate < 100
    - ``open``       : balanced, no JE matched yet
* ``posting_status`` — orthogonal to reconciliation:
    - ``posted``   : is_posted=True OR state == "posted"
    - ``unposted`` : everything else
  (a Tx can be reconciled-but-unposted -- common when the posting
  workflow lags. Treating posting as its own axis avoids hiding the
  reconciliation signal behind a missing flag.)
* ``due_status`` — one of:
    - ``no_due_date``  : Tx has no ``due_date``
    - ``paid``         : Tx fully reconciled, regardless of due_date
    - ``upcoming``     : due_date >= today (and not yet reconciled)
    - ``overdue``      : due_date < today (and not yet reconciled)
* ``severity`` — convenience sort key the UI uses to bring trouble
  to the top: 0=clean, 1=info (upcoming / unposted), 2=warning
  (partial), 3=danger (overdue / unbalanced).

The aggregate bucket counts the same Tx in EACH applicable status
(a Tx can be both ``unbalanced`` and ``overdue`` -- both rows count
+1). This lets the operator see "12 unbalanced AND 8 overdue" without
requiring exclusivity logic in the UI.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date as _date
from decimal import Decimal
from typing import Iterable, List, Optional

from django.db.models import Q

from accounting.models import Transaction

logger = logging.getLogger(__name__)


@dataclass
class TxStatusRow:
    id: int
    date: Optional[_date]
    amount: Decimal
    description: str
    due_date: Optional[_date]
    state: str
    is_posted: bool
    is_balanced: bool
    is_reconciled: bool
    reconciliation_rate: Decimal       # 0..100
    days_outstanding: Optional[int]
    days_overdue: Optional[int]
    recon_status: str                   # unbalanced / reconciled / partial / open
    posting_status: str                 # posted / unposted
    due_status: str                     # no_due_date / paid / upcoming / overdue
    severity: int                       # 0 clean .. 3 danger
    status_chips: List[str]             # all applicable chip labels for the row

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "amount": str(self.amount),
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "state": self.state,
            "is_posted": self.is_posted,
            "is_balanced": self.is_balanced,
            "is_reconciled": self.is_reconciled,
            "reconciliation_rate": str(self.reconciliation_rate),
            "days_outstanding": self.days_outstanding,
            "days_overdue": self.days_overdue,
            "recon_status": self.recon_status,
            "posting_status": self.posting_status,
            "due_status": self.due_status,
            "severity": self.severity,
            "status_chips": self.status_chips,
        }


def _classify(tx: Transaction, today: _date) -> TxStatusRow:
    """Pure classification of a single Tx into the derived dimensions.
    No DB writes; safe to call inside a list comprehension."""
    rate = Decimal(tx.reconciliation_rate or 0)
    state = tx.state or ""
    is_posted = bool(tx.is_posted) or state == "posted"
    is_balanced = bool(tx.is_balanced)
    is_reconciled = bool(tx.is_reconciled)

    # ---- recon_status (orthogonal to posting; data-quality first) ----
    if not is_balanced:
        recon_status = "unbalanced"
    elif is_reconciled:
        recon_status = "reconciled"
    elif rate > 0:
        recon_status = "partial"
    else:
        recon_status = "open"

    # ---- posting_status (separate axis) ----
    posting_status = "posted" if is_posted else "unposted"

    # ---- due_status + days_overdue ----
    days_overdue: Optional[int] = None
    if tx.due_date is None:
        due_status = "no_due_date"
    elif is_reconciled:
        due_status = "paid"
    elif tx.due_date >= today:
        due_status = "upcoming"
    else:
        due_status = "overdue"
        days_overdue = (today - tx.due_date).days

    # ---- severity (UI sort hint) ----
    if recon_status == "unbalanced" or due_status == "overdue":
        severity = 3
    elif recon_status == "partial":
        severity = 2
    elif posting_status == "unposted" or due_status == "upcoming":
        severity = 1
    else:
        severity = 0

    # ---- status chips: every applicable label, not just the primary ----
    chips: List[str] = [recon_status, posting_status]
    if due_status != "no_due_date":
        chips.append(due_status)

    return TxStatusRow(
        id=tx.id,
        date=tx.date,
        amount=Decimal(tx.amount or 0),
        description=tx.description or "",
        due_date=tx.due_date,
        state=state,
        is_posted=is_posted,
        is_balanced=is_balanced,
        is_reconciled=is_reconciled,
        reconciliation_rate=rate,
        days_outstanding=tx.days_outstanding,
        days_overdue=days_overdue,
        recon_status=recon_status,
        posting_status=posting_status,
        due_status=due_status,
        severity=severity,
        status_chips=chips,
    )


def compute_tx_status(
    company,
    *,
    date_from: Optional[_date] = None,
    date_to: Optional[_date] = None,
    entity_id: Optional[int] = None,
    cnpj: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
    limit: int = 200,
) -> dict:
    """Build a classified-Tx report for ``company``.

    Args:
        company: tenant.
        date_from / date_to: ``transaction.date`` window (inclusive).
            Default: last 90 days.
        entity_id / cnpj: optional scope filters mirroring the rest of
            the accounting reporting surface.
        statuses: optional iterable of ``recon_status`` or ``due_status``
            values; only rows that match at least one of these in
            ``status_chips`` are returned. Useful for "show me all
            overdue + unbalanced" without two API calls.
        limit: row cap (caller paginates beyond this).

    Returns ``{period, totals, aggregates, rows[], notes}``. Aggregates
    count the same Tx in EVERY applicable bucket (a Tx with both
    ``unbalanced`` and ``overdue`` chips counts +1 in each).
    """
    today = _date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        from datetime import timedelta
        date_from = today - timedelta(days=90)

    qs = Transaction.objects.filter(
        company=company,
        date__gte=date_from,
        date__lte=date_to,
    )
    if entity_id is not None:
        qs = qs.filter(entity_id=entity_id)
    if cnpj:
        digits = "".join(ch for ch in str(cnpj) if ch.isdigit())
        if digits:
            qs = qs.filter(cnpj=digits)
    qs = qs.order_by("-date", "-id")

    # Pull only the columns _classify actually reads; avoids hauling
    # the description embedding etc. on a 5k-row sweep.
    rows_qs = qs.only(
        "id", "date", "amount", "description", "state", "due_date",
        "is_balanced", "is_reconciled", "is_posted",
        "reconciliation_rate", "days_outstanding",
    )

    # Materialize lazily; aggregates can short-circuit to count() when
    # the caller didn't ask for rows. For now we always materialize
    # because the row cap (default 200) keeps it bounded; callers that
    # need bucket counts only can pass ``limit=0``.
    rows: List[TxStatusRow] = []
    aggregates: Counter = Counter()
    severity_counts: Counter = Counter()
    total_value = Decimal("0")
    n_total = 0

    wanted = set(statuses) if statuses else None

    # We classify everything for accurate aggregates -- the limit only
    # truncates the rows[] payload.
    for tx in rows_qs.iterator(chunk_size=500):
        n_total += 1
        total_value += Decimal(tx.amount or 0)
        row = _classify(tx, today)
        for chip in row.status_chips:
            aggregates[chip] += 1
        severity_counts[row.severity] += 1
        if wanted is None or any(c in wanted for c in row.status_chips):
            rows.append(row)

    # Sort returned rows by severity (highest first), then by date desc.
    rows.sort(key=lambda r: (-r.severity, -(r.date.toordinal() if r.date else 0)))
    truncated = len(rows) > limit
    rows = rows[:limit] if limit > 0 else []

    return {
        "period": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
        "totals": {
            "n_transactions": n_total,
            "total_amount": str(total_value),
        },
        "aggregates": {
            # recon_status buckets (mutually exclusive, one chip per Tx)
            "reconciled": aggregates.get("reconciled", 0),
            "partial": aggregates.get("partial", 0),
            "open": aggregates.get("open", 0),
            "unbalanced": aggregates.get("unbalanced", 0),
            # posting_status buckets (mutually exclusive)
            "posted": aggregates.get("posted", 0),
            "unposted": aggregates.get("unposted", 0),
            # due_status buckets (mutually exclusive)
            "paid": aggregates.get("paid", 0),
            "upcoming": aggregates.get("upcoming", 0),
            "overdue": aggregates.get("overdue", 0),
        },
        "by_severity": {
            "clean": severity_counts.get(0, 0),
            "info": severity_counts.get(1, 0),
            "warning": severity_counts.get(2, 0),
            "danger": severity_counts.get(3, 0),
        },
        "rows": [r.to_dict() for r in rows],
        "truncated": truncated,
        "notes": (
            "Aggregates count each Tx in every applicable bucket, so a "
            "transaction tagged ``unbalanced`` AND ``overdue`` "
            "contributes +1 to each. ``rows`` is sorted by severity "
            "(danger first) then by date desc."
        ),
    }
