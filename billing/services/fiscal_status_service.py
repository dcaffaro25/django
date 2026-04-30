# -*- coding: utf-8 -*-
"""
Computes Invoice.fiscal_status from the linked NF chain.

Fiscal status is a CACHE projected from authoritative state held on the NF
chain:
    - NotaFiscal.status_sefaz / NFeEvento (cancelamento)
    - NotaFiscalReferencia (devolução chains via finalidade=4)
    - InvoiceNFLink.relation_type (denormalized hint)

The Invoice's payment ``status`` (draft/issued/paid/...) is ORTHOGONAL and
left untouched by this service.

Trigger points (caller-driven, no signals — keeps accounting effects
traceable):
    - nfe_import_service.import_one         -> refresh_for_nf(nf)
    - nfe_event_import_service.import_event -> refresh_for_nf(event.nota_fiscal)
    - nf_link_service.accept_link           -> refresh_for_nf(link.nota_fiscal)
    - InvoiceNFLink.save                    -> refresh(invoice)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable

from django.utils import timezone

logger = logging.getLogger(__name__)


# Status enum (mirrors Invoice.FISCAL_STATUS_CHOICES keys)
PENDING_NF = "pending_nf"
INVOICED = "invoiced"
PARTIALLY_RETURNED = "partially_returned"
FULLY_RETURNED = "fully_returned"
FISCALLY_CANCELLED = "fiscally_cancelled"
MIXED = "mixed"

_RETURN_TOLERANCE = Decimal("0.01")  # R$ 0,01 to absorb rounding
_CANCEL_EVENT_TYPES = {110111, 110112}  # Cancelamento and Cancelamento por substituição
_CCe_EVENT_TYPE = 110110


def _nf_was_cancelled(nf) -> bool:
    """True when this NF has a registered cancelamento event."""
    try:
        return nf.eventos.filter(
            tipo_evento__in=list(_CANCEL_EVENT_TYPES),
            status_sefaz="135",  # 135 = Evento registrado e vinculado a NF-e (canonical "ok")
        ).exists() or nf.eventos.filter(
            tipo_evento__in=list(_CANCEL_EVENT_TYPES),
            status_sefaz="155",  # 155 = "Cancelamento homologado fora de prazo" — also valid
        ).exists()
    except Exception:
        # Falha em ler eventos -> assume não-cancelada (cache sempre safe-default).
        return False


def _nf_returned_amount(nf) -> Decimal:
    """
    Sum of valor_nota of devolução NFs (finalidade=4) that reference this NF.
    Returns 0 when there are no returns.
    """
    try:
        # NotaFiscalReferencia rows pointing AT this NF (notas_que_me_referenciam)
        referencing = nf.notas_que_me_referenciam.select_related("nota_fiscal").filter(
            nota_fiscal__finalidade=4,
        )
        total = Decimal("0")
        for ref in referencing:
            total += Decimal(ref.nota_fiscal.valor_nota or 0)
        return total
    except Exception:
        return Decimal("0")


def _nf_has_pending_cce(nf) -> bool:
    try:
        return nf.eventos.filter(tipo_evento=_CCe_EVENT_TYPE).exists()
    except Exception:
        return False


def _classify_single_nf(nf) -> tuple[str, dict]:
    """
    Classify one NF in isolation. Returns (status, breakdown).

    Breakdown keys:
        nf_id, chave, valor_nota, returned_amount, cancelled, has_cce
    """
    breakdown = {
        "nf_id": nf.id,
        "chave": nf.chave,
        "numero": nf.numero,
        "valor_nota": str(nf.valor_nota or 0),
        "returned_amount": "0",
        "cancelled": False,
        "has_cce": False,
    }

    if _nf_was_cancelled(nf):
        breakdown["cancelled"] = True
        return FISCALLY_CANCELLED, breakdown

    breakdown["has_cce"] = _nf_has_pending_cce(nf)

    valor = Decimal(nf.valor_nota or 0)
    returned = _nf_returned_amount(nf)
    breakdown["returned_amount"] = str(returned)

    if valor > 0 and returned >= valor - _RETURN_TOLERANCE:
        return FULLY_RETURNED, breakdown
    if returned > 0:
        return PARTIALLY_RETURNED, breakdown
    return INVOICED, breakdown


def compute_fiscal_status(invoice) -> tuple[str, dict]:
    """
    Aggregate fiscal status for an Invoice across all linked NFs.
    Returns (status_value, breakdown_dict) — breakdown is JSON-serializable
    and intended for UI tooltip / drill-down.
    """
    breakdown = {"per_nf": [], "has_pending_cce": False, "linked_nf_count": 0}

    nfs = list(invoice.notas_fiscais.all())
    breakdown["linked_nf_count"] = len(nfs)

    if not nfs:
        return PENDING_NF, breakdown

    statuses: list[str] = []
    for nf in nfs:
        s, b = _classify_single_nf(nf)
        statuses.append(s)
        breakdown["per_nf"].append(b)
        if b.get("has_cce"):
            breakdown["has_pending_cce"] = True

    if all(s == FISCALLY_CANCELLED for s in statuses):
        return FISCALLY_CANCELLED, breakdown
    if all(s == FULLY_RETURNED for s in statuses):
        return FULLY_RETURNED, breakdown
    if all(s == INVOICED for s in statuses):
        return INVOICED, breakdown

    # Heterogeneous — but a single "partially_returned" with no cancellations
    # and no other states deserves the partial label.
    unique = set(statuses)
    if unique == {PARTIALLY_RETURNED} or unique == {INVOICED, PARTIALLY_RETURNED}:
        return PARTIALLY_RETURNED, breakdown

    return MIXED, breakdown


def refresh(invoice, *, persist: bool = True) -> str:
    """
    Recompute and (by default) write back to invoice.fiscal_status. Returns
    the new status value. Idempotent.

    Also re-counts unacknowledged critics and stores the totals on the
    Invoice so list views can filter without per-row computation.
    """
    new_status, breakdown = compute_fiscal_status(invoice)
    has_cce = bool(breakdown.get("has_pending_cce"))

    if not persist:
        return new_status

    update_fields = []
    if invoice.fiscal_status != new_status:
        invoice.fiscal_status = new_status
        update_fields.append("fiscal_status")
    if invoice.has_pending_corrections != has_cce:
        invoice.has_pending_corrections = has_cce
        update_fields.append("has_pending_corrections")
    invoice.fiscal_status_computed_at = timezone.now()
    update_fields.append("fiscal_status_computed_at")

    # Critics tally — best-effort. Never block the fiscal_status save on this.
    try:
        from billing.services.critics_service import (
            compute_critics_for_invoice, annotate_acknowledgements, severity_counts,
        )
        critics = compute_critics_for_invoice(invoice)
        annotate_acknowledgements(invoice, critics)
        sev = severity_counts(critics, only_unacknowledged=True)
        new_count = sum(sev.values())
        if invoice.critics_count != new_count:
            invoice.critics_count = new_count
            update_fields.append("critics_count")
        if invoice.critics_count_by_severity != sev:
            invoice.critics_count_by_severity = sev
            update_fields.append("critics_count_by_severity")
    except Exception:
        logger.exception(
            "fiscal_status_service: critics tally failed for invoice_id=%s",
            invoice.id,
        )

    if update_fields:
        invoice.save(update_fields=update_fields)
        try:
            # Cache invalidation only when the status actually changed —
            # bumping on every recompute would defeat the cache.
            if "fiscal_status" in update_fields:
                from accounting.services.report_cache import bump_version
                bump_version(invoice.company_id)
        except Exception:
            logger.exception(
                "fiscal_status_service: bump_version failed for company_id=%s",
                invoice.company_id,
            )
    return new_status


def refresh_for_nf(nota_fiscal) -> list[int]:
    """
    Recompute fiscal_status for every Invoice linked to ``nota_fiscal``.
    Returns the list of refreshed Invoice IDs.
    """
    invoice_ids = list(nota_fiscal.invoices.values_list("id", flat=True))
    if not invoice_ids:
        return []
    from billing.models import Invoice
    refreshed: list[int] = []
    for inv in Invoice.objects.filter(company=nota_fiscal.company, id__in=invoice_ids):
        refresh(inv, persist=True)
        refreshed.append(inv.id)
    return refreshed


def refresh_many(invoices: Iterable) -> int:
    """Recompute fiscal_status for the given iterable of Invoices."""
    count = 0
    for inv in invoices:
        refresh(inv, persist=True)
        count += 1
    return count
