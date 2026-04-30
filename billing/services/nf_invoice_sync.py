# -*- coding: utf-8 -*-
"""
Bidirectional NF ↔ Invoice sync.

Two operations:

1. ``match_or_create_invoice_for_nf(nf)``
   When a new NF lands, try to find an existing Invoice that should "own" it.
   If found, attach via ``InvoiceNFLink``. Otherwise (and only when the
   tenant flag is on), create a new Invoice from NF data.

2. ``attach_invoice_to_nf(invoice, nf, *, relation_type)``
   Manual M:N attach helper — used by the UI's "link existing invoice" action.

Both operations refresh fiscal_status on affected Invoices.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Heurística: janela em torno da data de emissão para casar Invoice→NF.
_DEFAULT_DATE_WINDOW_DAYS = 30


def _digits(value: Optional[str]) -> str:
    if not value:
        return ""
    import re
    return re.sub(r"\D", "", str(value))


def _is_self_cnpj(cnpj: Optional[str], company) -> bool:
    """
    True when ``cnpj`` belongs to the tenant itself (matriz or filial).
    Compared by 8-digit CNPJ root since filiais share the matriz root —
    avoids requiring every filial CNPJ to be configured on the tenant.
    """
    if not cnpj or not company or not company.cnpj:
        return False
    cnpj_digits = _digits(cnpj)
    own_digits = _digits(company.cnpj)
    if len(cnpj_digits) != 14 or len(own_digits) != 14:
        return False
    return cnpj_digits[:8] == own_digits[:8]


def _resolve_partner_for_nf(nf) -> Optional[object]:
    """
    Return the BusinessPartner that represents the *counterparty* on a
    generated Invoice — never the tenant itself.

    Drops the candidate whose CNPJ matches the tenant root (matriz or
    filial), so an NF where evolat is the destinatario doesn't generate
    an Invoice billing evolat against itself.
    """
    company = nf.company
    if nf.tipo_operacao == 1:  # saída → counterparty is destinatário
        primary, secondary = nf.destinatario, nf.emitente
        primary_cnpj, secondary_cnpj = nf.dest_cnpj, nf.emit_cnpj
    else:  # entrada → counterparty is emitente
        primary, secondary = nf.emitente, nf.destinatario
        primary_cnpj, secondary_cnpj = nf.emit_cnpj, nf.dest_cnpj

    if primary is not None and not _is_self_cnpj(primary_cnpj, company):
        return primary
    if secondary is not None and not _is_self_cnpj(secondary_cnpj, company):
        return secondary
    # Both sides are the tenant itself (self-transfer between branches) or
    # no FK resolved — return None so the caller records a skip.
    return None


def _invoice_type_for_nf(nf) -> str:
    return "sale" if nf.tipo_operacao == 1 else "purchase"


def _find_match(nf, *, date_window_days: int = _DEFAULT_DATE_WINDOW_DAYS):
    """
    Search for an existing Invoice that should attach to ``nf``.

    Match preference:
    1. invoice_number == NF.numero AND partner.identifier ∈ {emit_cnpj, dest_cnpj}
    2. partner match + total_amount within tolerance + date window
    Falls back to None when nothing convincing is found.
    """
    from billing.models import Invoice

    company = nf.company
    partner_candidates_cnpjs = {_digits(nf.emit_cnpj), _digits(nf.dest_cnpj)}
    partner_candidates_cnpjs.discard("")

    qs = Invoice.objects.filter(company=company).exclude(status="canceled")
    qs = qs.filter(partner__identifier__in=list(partner_candidates_cnpjs)) if partner_candidates_cnpjs else qs

    # Hard match: invoice_number == numero (string comparison; numero is int)
    nf_numero_str = str(nf.numero)
    by_number = qs.filter(invoice_number=nf_numero_str).first()
    if by_number is not None:
        return by_number

    # Soft match: same partner + amount within 1% + same month
    nf_date = nf.data_emissao.date() if nf.data_emissao else None
    if nf_date is None:
        return None
    date_low = nf_date - timedelta(days=date_window_days)
    date_high = nf_date + timedelta(days=date_window_days)
    candidates = qs.filter(invoice_date__range=(date_low, date_high))

    nf_total = Decimal(nf.valor_nota or 0)
    if nf_total <= 0:
        return None
    tol = Decimal("0.01")  # 1%
    for inv in candidates:
        try:
            inv_total = Decimal(inv.total_amount or 0)
            if inv_total <= 0:
                continue
            if abs(inv_total - nf_total) / nf_total <= tol:
                return inv
        except Exception:
            continue
    return None


def _is_eligible_for_auto_create(nf, config) -> bool:
    """Tenant policy gate. False = skip auto-create."""
    if not config.auto_create_invoice_from_nf:
        return False
    if nf.tipo_operacao not in config.allowed_tipos_operacao():
        return False
    if nf.finalidade not in config.allowed_finalidades():
        return False
    return True


def _create_invoice_from_nf(nf):
    """Build a draft Invoice mirroring NF totals + partner. Does NOT save
    lines. Returns None when no counterparty resolves (self-billing or
    missing partner FK)."""
    from billing.models import Invoice

    partner = _resolve_partner_for_nf(nf)
    if partner is None:
        return None

    invoice = Invoice.objects.create(
        company=nf.company,
        partner=partner,
        invoice_type=_invoice_type_for_nf(nf),
        invoice_number=str(nf.numero),
        invoice_date=nf.data_emissao.date() if nf.data_emissao else timezone.now().date(),
        due_date=nf.data_emissao.date() if nf.data_emissao else timezone.now().date(),
        status="issued",
        total_amount=nf.valor_nota or 0,
        tax_amount=(
            Decimal(nf.valor_icms or 0)
            + Decimal(nf.valor_pis or 0)
            + Decimal(nf.valor_cofins or 0)
            + Decimal(nf.valor_ipi or 0)
        ),
        discount_amount=nf.valor_desconto or 0,
        description=f"Auto-criada a partir da NF {nf.numero} ({nf.chave[-8:]})",
    )
    return invoice


def _relation_type_for_nf(nf) -> str:
    """Map NF.finalidade → InvoiceNFLink.relation_type."""
    from billing.models import InvoiceNFLink
    if nf.finalidade == 4:
        return InvoiceNFLink.REL_DEVOLUCAO
    if nf.finalidade == 2:
        return InvoiceNFLink.REL_COMPLEMENTAR
    if nf.finalidade == 3:
        return InvoiceNFLink.REL_AJUSTE
    return InvoiceNFLink.REL_NORMAL


def attach_invoice_to_nf(invoice, nf, *, relation_type: Optional[str] = None,
                         allocated_amount=None, notes: str = ""):
    """Idempotent M:N attach. Triggers fiscal_status refresh.

    When the Invoice's ``partner`` differs from the NF's resolved
    counterparty BP, also raises a BP-Group suggestion — common when the
    Invoice was created earlier from one document (e.g. a bank deposit
    showing the acquirer's CNPJ) but the NF carries the actual customer
    CNPJ.
    """
    from billing.models import InvoiceNFLink
    if invoice.company_id != nf.company_id:
        raise ValueError("Invoice e NF de tenants diferentes; recusando attach.")
    rel_type = relation_type or _relation_type_for_nf(nf)
    link, created = InvoiceNFLink.objects.get_or_create(
        company=invoice.company,
        invoice=invoice,
        nota_fiscal=nf,
        defaults={
            "relation_type": rel_type,
            "allocated_amount": allocated_amount,
            "notes": notes,
        },
    )
    # Refresh fiscal_status for the affected Invoice(s)
    try:
        from billing.services.fiscal_status_service import refresh
        refresh(invoice, persist=True)
    except Exception:
        logger.exception("attach_invoice_to_nf: fiscal_status.refresh failed for invoice_id=%s", invoice.id)
    # Suggest BP-Group when invoice partner ≠ NF counterparty.
    try:
        nf_partner = _resolve_partner_for_nf(nf)
        inv_partner = invoice.partner
        if (
            nf_partner is not None
            and inv_partner is not None
            and nf_partner.id != inv_partner.id
        ):
            from billing.services.bp_group_service import (
                upsert_membership_suggestion,
            )
            upsert_membership_suggestion(
                inv_partner, nf_partner,
                method="nf_invoice_attach",
                source_id=invoice.id,
                confidence=Decimal("0.75"),
            )
    except Exception:
        logger.exception(
            "attach_invoice_to_nf: bp_group suggest failed for invoice_id=%s",
            invoice.id,
        )
    return link, created


def auto_attach_devolucao_to_parent_invoice(nf) -> int:
    """
    For a devolução NF (finalidade=4), find every Invoice whose linked NFs
    include any of the NFs this devolução references, and attach the
    devolução with relation_type='devolucao'.

    Returns the number of attachments created. Idempotent — re-running on
    an already-attached devolução produces zero new attachments.
    """
    from billing.models import Invoice, InvoiceNFLink, NotaFiscalReferencia

    if nf.finalidade != 4:
        return 0

    # Collect referenced original NFs
    refs = list(
        NotaFiscalReferencia.objects
        .filter(company=nf.company, nota_fiscal=nf)
        .values_list("nota_referenciada_id", flat=True)
    )
    referenced_ids = [r for r in refs if r is not None]
    if not referenced_ids:
        return 0

    # Invoices that have any of those NFs M2M-attached
    parent_invoices = list(
        Invoice.objects
        .filter(company=nf.company, notas_fiscais__id__in=referenced_ids)
        .distinct()
    )
    if not parent_invoices:
        return 0

    created = 0
    for inv in parent_invoices:
        link, was_created = InvoiceNFLink.objects.get_or_create(
            company=inv.company,
            invoice=inv,
            nota_fiscal=nf,
            defaults={
                "relation_type": InvoiceNFLink.REL_DEVOLUCAO,
                "notes": "Auto-vinculado pela importação (devolução referencia NF da fatura).",
            },
        )
        if was_created:
            created += 1
            try:
                from billing.services.fiscal_status_service import refresh
                refresh(inv, persist=True)
            except Exception:
                logger.exception(
                    "auto_attach_devolucao: fiscal_status.refresh failed for invoice_id=%s",
                    inv.id,
                )
    return created


@db_transaction.atomic
def match_or_create_invoice_for_nf(
    nf, *, dry_run: bool = False, force: bool = False,
) -> dict:
    """
    Top-level entry point called by the NF importer.

    Args:
        dry_run: simulate without persisting (matched/created Invoice
            references are returned as sentinels in this mode).
        force: bypass ``BillingTenantConfig.auto_create_invoice_from_nf``
            and the finalidade/tipo whitelist. Used by targeted backfill
            commands that have their own filtering logic upstream.

    Returns:
        {
          "matched_invoice_id": int | None,
          "created_invoice_id": int | None,
          "link_id": int | None,
          "skipped_reason": str | None,
          "dry_run": bool,
        }
    """
    from billing.models import BillingTenantConfig

    out = {
        "matched_invoice_id": None,
        "created_invoice_id": None,
        "link_id": None,
        "skipped_reason": None,
        "dry_run": dry_run,
    }

    config = BillingTenantConfig.get_or_default(nf.company)

    matched = _find_match(nf)
    if matched is not None:
        out["matched_invoice_id"] = matched.id
        if not dry_run:
            link, _ = attach_invoice_to_nf(matched, nf)
            out["link_id"] = link.id
        return out

    if not force and not _is_eligible_for_auto_create(nf, config):
        out["skipped_reason"] = (
            "auto_create_disabled"
            if not config.auto_create_invoice_from_nf
            else "tipo_or_finalidade_filtered"
        )
        return out

    # Self-billing guard: even with force=True, never create an Invoice
    # where the tenant bills itself. Surfaces as a distinct skip reason
    # so backfill reports show the count.
    partner = _resolve_partner_for_nf(nf)
    if partner is None:
        out["skipped_reason"] = "no_counterparty_or_self_billing"
        return out

    if dry_run:
        out["created_invoice_id"] = -1  # sentinel for preview
        return out

    invoice = _create_invoice_from_nf(nf)
    if invoice is None:
        out["skipped_reason"] = "no_partner_resolved"
        return out
    out["created_invoice_id"] = invoice.id
    link, _ = attach_invoice_to_nf(invoice, nf)
    out["link_id"] = link.id
    return out
