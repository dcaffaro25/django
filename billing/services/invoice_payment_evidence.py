# -*- coding: utf-8 -*-
"""
Invoice payment-evidence service.

Walks ``Invoice → InvoiceNFLink → NotaFiscal → NFTransactionLink →
Transaction.is_reconciled`` to answer the question "did the cash
actually move for this invoice, regardless of what
``Invoice.status`` says".

The Invoice payment status is set at issue time and (today) never
re-derived from downstream cash signals. So an invoice can be marked
``issued`` indefinitely while in fact the payment landed, the bank
tx was matched, and the matching NF↔Tx link was accepted by an
operator. The evidence walk surfaces those cases.

Three places consume this:

1. **DSO report** — adds a per-row ``payment_evidence_status``
   dimension so operators see "we say open but cash matched".
2. **Backfill mgmt command + API endpoint** — promotes invoices
   with ``cash_matched_full`` evidence to ``paid``.
3. **Auto-update hooks** — same evidence check, run synchronously
   when an NF↔Tx link is accepted or a Reconciliation finalize
   flips ``Tx.is_reconciled``.

All three share ``classify_invoice_payment_evidence(invoice)`` to
keep the rule in one place.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional

from accounting.models import Transaction
from billing.models import Invoice, InvoiceNFLink, NFTransactionLink

logger = logging.getLogger(__name__)


# Five-state classification per invoice. Mutually exclusive; every
# invoice lands in exactly one bucket.
EVIDENCE_CASH_MATCHED_FULL = "cash_matched_full"
EVIDENCE_CASH_MATCHED_PARTIAL = "cash_matched_partial"
EVIDENCE_LINKED_NO_RECON = "linked_no_recon"
EVIDENCE_NF_LINKED_NO_TX = "nf_linked_no_tx"
EVIDENCE_UNLINKED = "unlinked"

EVIDENCE_CHOICES = (
    EVIDENCE_CASH_MATCHED_FULL,
    EVIDENCE_CASH_MATCHED_PARTIAL,
    EVIDENCE_LINKED_NO_RECON,
    EVIDENCE_NF_LINKED_NO_TX,
    EVIDENCE_UNLINKED,
)


@dataclass
class PaymentEvidence:
    """Result of the Invoice payment-evidence walk."""
    invoice_id: int
    status: str                                 # one of EVIDENCE_*
    nf_count: int
    tx_count: int
    reconciled_tx_count: int
    linked_tx_ids: List[int]

    @property
    def is_likely_paid(self) -> bool:
        """True when ``cash_matched_full`` -- the strict signal the
        backfill / auto-update hook keys on."""
        return self.status == EVIDENCE_CASH_MATCHED_FULL

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "status": self.status,
            "nf_count": self.nf_count,
            "tx_count": self.tx_count,
            "reconciled_tx_count": self.reconciled_tx_count,
            "linked_tx_ids": self.linked_tx_ids,
        }


def classify_invoice_payment_evidence(invoice: Invoice) -> PaymentEvidence:
    """Single-invoice walk. Used by reports + per-event hooks."""
    nf_ids = list(
        InvoiceNFLink.objects
        .filter(invoice=invoice)
        .values_list("nota_fiscal_id", flat=True)
    )
    if not nf_ids:
        return PaymentEvidence(
            invoice_id=invoice.id,
            status=EVIDENCE_UNLINKED,
            nf_count=0, tx_count=0, reconciled_tx_count=0,
            linked_tx_ids=[],
        )

    tx_ids = list(
        NFTransactionLink.objects
        .filter(
            nota_fiscal_id__in=nf_ids,
            review_status=NFTransactionLink.REVIEW_ACCEPTED,
        )
        .values_list("transaction_id", flat=True)
        .distinct()
    )
    if not tx_ids:
        return PaymentEvidence(
            invoice_id=invoice.id,
            status=EVIDENCE_NF_LINKED_NO_TX,
            nf_count=len(nf_ids), tx_count=0, reconciled_tx_count=0,
            linked_tx_ids=[],
        )

    txs = list(Transaction.objects.filter(id__in=tx_ids).only("id", "is_reconciled"))
    n_recon = sum(1 for t in txs if t.is_reconciled)
    if n_recon == len(txs) and txs:
        status = EVIDENCE_CASH_MATCHED_FULL
    elif n_recon > 0:
        status = EVIDENCE_CASH_MATCHED_PARTIAL
    else:
        status = EVIDENCE_LINKED_NO_RECON
    return PaymentEvidence(
        invoice_id=invoice.id,
        status=status,
        nf_count=len(nf_ids),
        tx_count=len(txs),
        reconciled_tx_count=n_recon,
        linked_tx_ids=[t.id for t in txs],
    )


def classify_many(invoices: Iterable[Invoice]) -> dict[int, PaymentEvidence]:
    """Batch version optimized for reports — three queries total
    (NF links, Tx links, Tx flags) instead of three per invoice."""
    invs = list(invoices)
    if not invs:
        return {}
    inv_ids = [i.id for i in invs]

    # NF links per invoice
    nf_by_inv: dict[int, list[int]] = {iid: [] for iid in inv_ids}
    for r in InvoiceNFLink.objects.filter(invoice_id__in=inv_ids).values(
        "invoice_id", "nota_fiscal_id",
    ):
        nf_by_inv[r["invoice_id"]].append(r["nota_fiscal_id"])

    # All NFs we'll touch
    all_nf_ids: set[int] = set()
    for ids in nf_by_inv.values():
        all_nf_ids.update(ids)

    # Tx links per NF (accepted only)
    tx_by_nf: dict[int, list[int]] = {nfid: [] for nfid in all_nf_ids}
    for r in NFTransactionLink.objects.filter(
        nota_fiscal_id__in=list(all_nf_ids),
        review_status=NFTransactionLink.REVIEW_ACCEPTED,
    ).values("nota_fiscal_id", "transaction_id"):
        tx_by_nf[r["nota_fiscal_id"]].append(r["transaction_id"])

    # Reconciled flag per Tx
    all_tx_ids: set[int] = set()
    for ids in tx_by_nf.values():
        all_tx_ids.update(ids)
    recon_by_tx: dict[int, bool] = {
        r["id"]: bool(r["is_reconciled"])
        for r in Transaction.objects.filter(id__in=list(all_tx_ids)).values(
            "id", "is_reconciled",
        )
    }

    out: dict[int, PaymentEvidence] = {}
    for inv in invs:
        nf_ids = nf_by_inv.get(inv.id, [])
        if not nf_ids:
            out[inv.id] = PaymentEvidence(
                invoice_id=inv.id,
                status=EVIDENCE_UNLINKED,
                nf_count=0, tx_count=0, reconciled_tx_count=0,
                linked_tx_ids=[],
            )
            continue
        tx_ids: set[int] = set()
        for nfid in nf_ids:
            tx_ids.update(tx_by_nf.get(nfid, []))
        if not tx_ids:
            out[inv.id] = PaymentEvidence(
                invoice_id=inv.id,
                status=EVIDENCE_NF_LINKED_NO_TX,
                nf_count=len(nf_ids), tx_count=0, reconciled_tx_count=0,
                linked_tx_ids=[],
            )
            continue
        n_recon = sum(1 for tid in tx_ids if recon_by_tx.get(tid, False))
        if n_recon == len(tx_ids):
            status = EVIDENCE_CASH_MATCHED_FULL
        elif n_recon > 0:
            status = EVIDENCE_CASH_MATCHED_PARTIAL
        else:
            status = EVIDENCE_LINKED_NO_RECON
        out[inv.id] = PaymentEvidence(
            invoice_id=inv.id,
            status=status,
            nf_count=len(nf_ids),
            tx_count=len(tx_ids),
            reconciled_tx_count=n_recon,
            linked_tx_ids=sorted(tx_ids),
        )
    return out


def backfill_invoice_status_from_recon(
    company,
    *,
    only_open: bool = True,
    dry_run: bool = False,
) -> dict:
    """Promote ``Invoice.status`` to ``paid`` for invoices whose
    payment evidence is ``cash_matched_full``.

    Args:
        company: tenant.
        only_open: when True (default), only consider invoices in
            status ``issued`` or ``partially_paid``. Set False to
            re-evaluate all sale invoices (e.g. after a model
            migration).
        dry_run: don't write; return counters as if we had.

    Returns counter dict with totals + samples for the operator's
    confirmation step.
    """
    qs = Invoice.objects.filter(company=company, invoice_type="sale")
    if only_open:
        qs = qs.filter(status__in=("issued", "partially_paid"))
    invs = list(qs.only("id", "status", "total_amount", "invoice_number"))
    evidence = classify_many(invs)

    counters = {
        "scanned": len(invs),
        "would_promote": 0,
        "promoted": 0,
        "by_evidence": {k: 0 for k in EVIDENCE_CHOICES},
        "promoted_amount": Decimal("0"),
        "samples": [],
    }
    promoted_ids: list[int] = []
    sample_buf: list[dict] = []

    for inv in invs:
        ev = evidence.get(inv.id)
        if ev is None:
            continue
        counters["by_evidence"][ev.status] += 1
        if ev.status == EVIDENCE_CASH_MATCHED_FULL:
            counters["would_promote"] += 1
            counters["promoted_amount"] += Decimal(inv.total_amount or 0)
            promoted_ids.append(inv.id)
            if len(sample_buf) < 6:
                sample_buf.append({
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "amount": str(inv.total_amount),
                    "old_status": inv.status,
                    "tx_ids": ev.linked_tx_ids,
                })

    counters["samples"] = sample_buf
    counters["promoted_amount"] = str(counters["promoted_amount"])

    if dry_run or not promoted_ids:
        return counters

    n = Invoice.objects.filter(id__in=promoted_ids).update(status="paid")
    counters["promoted"] = n

    # Cache hop -- the report cache reads Invoice through dashboard
    # KPIs but isn't keyed on Invoice changes today, so a bump_version
    # here would over-invalidate. Skipping; revisit if a future report
    # starts depending on Invoice.status freshness.
    return counters


def reevaluate_invoice_status_from_evidence(invoice: Invoice) -> Optional[str]:
    """Single-invoice version called from accept-link / reconciliation
    finalize hooks. Returns the new status if it changed, else None.

    Idempotent and best-effort: silent on any unexpected condition so
    the caller (which is in a critical accept / reconcile path) is
    never broken by a status update.
    """
    try:
        if invoice.invoice_type != "sale":
            return None
        if invoice.status not in ("issued", "partially_paid"):
            return None  # already paid or canceled or draft
        ev = classify_invoice_payment_evidence(invoice)
        if ev.status != EVIDENCE_CASH_MATCHED_FULL:
            return None
        Invoice.objects.filter(pk=invoice.pk).update(status="paid")
        logger.info(
            "invoice_payment_evidence: auto-promoted Invoice#%s -> paid "
            "(cash_matched_full, %d tx)",
            invoice.id, ev.reconciled_tx_count,
        )
        return "paid"
    except Exception:
        logger.exception(
            "invoice_payment_evidence: re-evaluation failed for Invoice#%s",
            getattr(invoice, "id", None),
        )
        return None
