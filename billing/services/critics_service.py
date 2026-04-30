# -*- coding: utf-8 -*-
"""
Critics engine for Invoice ↔ NotaFiscal coherence.

Brazilian retail/distribution operations frequently produce edge cases that
look like data errors but are actually legitimate operational patterns —
the canonical one being a sale of N "caixas" (bundles) followed by a
return of M "unidades" individuais. The fiscal_status logic operates on
NF totals (`Σ devolução.valor_nota`) which catches the value side, but
loses the item-level signal that could tell an operator "this is a bundle
expansion, not a typo".

This module computes a list of ``Critic`` records by walking the NF chain
attached to an Invoice and applying a small set of rules. It is purely
read-side: never mutates Invoice / NF / GL state.

Surfaces:
- ``GET /api/invoices/<id>/critics/`` returns the live list.
- The UI shows them grouped by severity inside the InvoiceDetailDrawer
  and surfaces a count next to the fiscal status badge.

Critic kinds (severity in parens):
- ``over_returned`` (error): Σ devolução.valor_nota > original.valor_nota + tolerance.
- ``quantity_over_returned`` (warning): per-code returned qty > sold qty.
- ``unit_price_drift`` (warning|info): per-code unit price diverges between sale and devolução.
- ``bundle_expansion_suspected`` (info): codes differ between sale and devolução but
  totals match — classic bundle/unit pattern.
- ``ncm_drift`` (warning): same code, different NCM.
- ``produto_unresolved`` (info): NotaFiscalItem.produto is NULL.

Tolerance defaults are chosen for typical NFe rounding (centavos) and
discount handling. They're parameters on ``compute_critics_for_invoice``
so per-tenant overrides remain trivial.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

KIND_OVER_RETURNED = "over_returned"
KIND_QUANTITY_OVER_RETURNED = "quantity_over_returned"
KIND_UNIT_PRICE_DRIFT = "unit_price_drift"
KIND_BUNDLE_EXPANSION = "bundle_expansion_suspected"
KIND_NCM_DRIFT = "ncm_drift"
KIND_PRODUTO_UNRESOLVED = "produto_unresolved"


@dataclass
class Critic:
    """One coherence finding. JSON-serializable via ``asdict``."""
    kind: str
    severity: str
    message: str
    subject_type: str  # "invoice" | "nota_fiscal" | "nota_fiscal_item"
    subject_id: int
    evidence: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False  # set by mark_acknowledged() after lookup
    acknowledged_at: str | None = None
    acknowledged_by_email: str | None = None
    acknowledged_note: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _D(v) -> Decimal:
    """Coerce to Decimal, returning Decimal(0) on garbage."""
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _related_devolucoes(orig_nf, all_dev_nfs):
    """Return the subset of devolução NFs (already filtered to
    finalidade=4) that reference ``orig_nf`` either via NotaFiscalReferencia
    chain or via the NF being directly listed in chave_referenciada."""
    out = []
    for d in all_dev_nfs:
        for ref in d.referencias_a_outras_notas.all():
            if ref.nota_referenciada_id == orig_nf.id or ref.chave_referenciada == orig_nf.chave:
                out.append(d)
                break
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_critics_for_invoice(
    invoice,
    *,
    value_tolerance: Decimal = Decimal("0.02"),  # 2% — covers NFe rounding
    quantity_tolerance: Decimal = Decimal("0.01"),  # 1% on quantity
    unit_price_warn_pct: Decimal = Decimal("0.10"),  # 10% triggers info
    unit_price_alarm_pct: Decimal = Decimal("0.30"),  # 30% triggers warning
) -> list[Critic]:
    """
    Walk the Invoice's linked NFs (originals + devoluções) and return a
    list of Critics. Stable order: errors first, then warnings, then info.

    Important: devolução NFs that reference an original NF via
    ``NotaFiscalReferencia`` are included in the analysis even when they
    are NOT attached to the Invoice's M2M. This mirrors fiscal_status's
    behavior and is what makes critics work today: the import flow's
    eligibility filter currently skips devoluções (finalidade=4), so the
    M2M only contains originals — but the reference chain is always
    populated by the importer.
    """
    from billing.models import NotaFiscal

    critics: list[Critic] = []
    attached = list(
        invoice.notas_fiscais.prefetch_related("itens", "referencias_a_outras_notas").all()
    )
    if not attached:
        return critics

    originals = [nf for nf in attached if nf.finalidade == 1]

    # Pull devolução NFs from the reference chain — covers the case where
    # they were imported but never auto-attached to the Invoice.
    devolucoes_via_chain: dict[int, list] = {}
    for orig in originals:
        related = list(
            NotaFiscal.objects
            .filter(
                company=invoice.company,
                finalidade=4,
                referencias_a_outras_notas__nota_referenciada=orig,
            )
            .prefetch_related("itens", "referencias_a_outras_notas")
            .distinct()
        )
        # Also include any devolução NF attached directly to the Invoice
        # that references this original — the union covers both paths.
        for nf in attached:
            if nf.finalidade == 4 and nf not in related:
                for ref in nf.referencias_a_outras_notas.all():
                    if ref.nota_referenciada_id == orig.id or ref.chave_referenciada == orig.chave:
                        related.append(nf)
                        break
        devolucoes_via_chain[orig.id] = related

    # Unresolved produto across the whole linked NF set — independent of
    # devolução logic so it always runs.
    for nf in attached:
        unresolved_count = sum(1 for it in nf.itens.all() if it.produto_id is None)
        if unresolved_count > 0:
            critics.append(Critic(
                kind=KIND_PRODUTO_UNRESOLVED,
                severity=SEVERITY_INFO,
                message=(
                    f"NF {nf.numero}: {unresolved_count} item(ns) sem produto "
                    "cadastrado — códigos não resolveram para um ProductService."
                ),
                subject_type="nota_fiscal",
                subject_id=nf.id,
                evidence={"unresolved_count": unresolved_count},
            ))

    # Per-original-NF analysis (only meaningful when there are devoluções)
    for orig in originals:
        related_devs = devolucoes_via_chain.get(orig.id, [])
        if not related_devs:
            continue

        critics.extend(_critics_for_nf_pair(
            orig, related_devs,
            value_tolerance=value_tolerance,
            quantity_tolerance=quantity_tolerance,
            unit_price_warn_pct=unit_price_warn_pct,
            unit_price_alarm_pct=unit_price_alarm_pct,
        ))

    return _sort_critics(critics)


def _critics_for_nf_pair(orig, related_devs, **opts) -> list[Critic]:
    """Generate critics for one (original NF, [devolução NFs]) pair."""
    out: list[Critic] = []
    value_tol = opts["value_tolerance"]
    qty_tol = opts["quantity_tolerance"]
    up_warn = opts["unit_price_warn_pct"]
    up_alarm = opts["unit_price_alarm_pct"]

    orig_total = _D(orig.valor_nota)
    ret_total = sum((_D(d.valor_nota) for d in related_devs), Decimal("0"))

    # 1. Total value over-return
    if orig_total > 0 and ret_total > orig_total * (Decimal("1") + value_tol):
        out.append(Critic(
            kind=KIND_OVER_RETURNED,
            severity=SEVERITY_ERROR,
            message=(
                f"NF {orig.numero}: devoluções somam R$ {ret_total} > "
                f"NF original R$ {orig_total}."
            ),
            subject_type="nota_fiscal",
            subject_id=orig.id,
            evidence={
                "original_total": str(orig_total),
                "returned_total": str(ret_total),
                "delta": str(ret_total - orig_total),
                "devolucao_ids": [d.id for d in related_devs],
            },
        ))

    # 2. Item-level analysis
    orig_items = list(orig.itens.all())
    orig_items_by_code: dict[str, list] = {}
    for it in orig_items:
        orig_items_by_code.setdefault(it.codigo_produto, []).append(it)

    all_dev_items = []
    for d in related_devs:
        all_dev_items.extend(d.itens.all())
    dev_items_by_code: dict[str, list] = {}
    for it in all_dev_items:
        dev_items_by_code.setdefault(it.codigo_produto, []).append(it)

    orig_codes = set(orig_items_by_code.keys())
    dev_codes = set(dev_items_by_code.keys())

    only_in_orig = orig_codes - dev_codes
    only_in_dev = dev_codes - orig_codes
    in_both = orig_codes & dev_codes

    # 3. Bundle expansion: codes differ + values close
    value_close = (
        orig_total > 0
        and abs(ret_total - orig_total) / orig_total <= value_tol
    )
    if only_in_orig and only_in_dev and value_close:
        out.append(Critic(
            kind=KIND_BUNDLE_EXPANSION,
            severity=SEVERITY_INFO,
            message=(
                f"NF {orig.numero}: códigos diferentes entre venda e devolução com "
                f"valores próximos (R$ {orig_total} → R$ {ret_total}). "
                "Possível bundle: venda em caixa, devolução por unidade."
            ),
            subject_type="nota_fiscal",
            subject_id=orig.id,
            evidence={
                "codes_only_in_original": sorted(only_in_orig)[:20],
                "codes_only_in_devolucao": sorted(only_in_dev)[:20],
                "original_total": str(orig_total),
                "returned_total": str(ret_total),
            },
        ))

    # 4. Per-matched-code critics
    for code in in_both:
        for orig_item in orig_items_by_code[code]:
            matched = dev_items_by_code[code]

            ret_qty = sum((_D(it.quantidade) for it in matched), Decimal("0"))
            ret_val = sum((_D(it.valor_total) for it in matched), Decimal("0"))
            orig_qty = _D(orig_item.quantidade)
            orig_val = _D(orig_item.valor_total)

            # 4a. Quantity over-return
            if orig_qty > 0 and ret_qty > orig_qty * (Decimal("1") + qty_tol):
                pct = ((ret_qty - orig_qty) / orig_qty * 100)
                out.append(Critic(
                    kind=KIND_QUANTITY_OVER_RETURNED,
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Item «{(orig_item.descricao or '')[:60]}»: vendido "
                        f"{orig_qty} {orig_item.unidade}, devolvido {ret_qty} "
                        f"({pct:+.0f}%)."
                    ),
                    subject_type="nota_fiscal_item",
                    subject_id=orig_item.id,
                    evidence={
                        "code": code,
                        "sold_qty": str(orig_qty),
                        "returned_qty": str(ret_qty),
                        "delta_pct": f"{pct:.2f}",
                    },
                ))

            # 4b. Unit-price drift
            if orig_qty > 0 and ret_qty > 0:
                orig_unit = orig_val / orig_qty
                ret_unit = ret_val / ret_qty
                if orig_unit > 0:
                    drift = (ret_unit - orig_unit) / orig_unit
                    abs_drift = abs(drift)
                    if abs_drift >= up_warn:
                        sev = SEVERITY_WARNING if abs_drift >= up_alarm else SEVERITY_INFO
                        pct = drift * 100
                        out.append(Critic(
                            kind=KIND_UNIT_PRICE_DRIFT,
                            severity=sev,
                            message=(
                                f"Item «{(orig_item.descricao or '')[:60]}»: "
                                f"preço unitário R$ {orig_unit:.4f} (venda) → "
                                f"R$ {ret_unit:.4f} (devolução) ({pct:+.1f}%)."
                            ),
                            subject_type="nota_fiscal_item",
                            subject_id=orig_item.id,
                            evidence={
                                "code": code,
                                "original_unit_price": str(orig_unit.quantize(Decimal("0.0001"))),
                                "return_unit_price": str(ret_unit.quantize(Decimal("0.0001"))),
                                "drift_pct": f"{pct:.4f}",
                            },
                        ))

            # 4c. NCM drift
            ret_ncms = {it.ncm for it in matched if it.ncm}
            if ret_ncms and orig_item.ncm and orig_item.ncm not in ret_ncms:
                out.append(Critic(
                    kind=KIND_NCM_DRIFT,
                    severity=SEVERITY_WARNING,
                    message=(
                        f"Item «{(orig_item.descricao or '')[:60]}»: NCM venda "
                        f"{orig_item.ncm} ≠ NCM devolução {sorted(ret_ncms)}."
                    ),
                    subject_type="nota_fiscal_item",
                    subject_id=orig_item.id,
                    evidence={
                        "code": code,
                        "original_ncm": orig_item.ncm,
                        "return_ncms": sorted(ret_ncms),
                    },
                ))

    return out


def _sort_critics(critics: Iterable[Critic]) -> list[Critic]:
    """Acknowledged last; within each group, errors → warnings → info, then by kind."""
    sev_order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
    return sorted(
        critics,
        key=lambda c: (1 if c.acknowledged else 0, sev_order.get(c.severity, 99), c.kind),
    )


def critics_to_dict(critics: Iterable[Critic]) -> list[dict]:
    """Convenience: serialize for JSON response."""
    return [asdict(c) for c in critics]


def annotate_acknowledgements(invoice, critics: list[Critic]) -> list[Critic]:
    """
    Stamp each critic with its acknowledgement state by querying
    CriticAcknowledgement for matching (kind, subject_type, subject_id).
    Critics are returned in-place, mutated.
    """
    if not critics:
        return critics
    from billing.models import CriticAcknowledgement
    keys = {(c.kind, c.subject_type, c.subject_id) for c in critics}
    if not keys:
        return critics
    acks = list(
        CriticAcknowledgement.objects
        .filter(company=invoice.company, invoice=invoice)
        .select_related("acknowledged_by")
    )
    by_key = {(a.kind, a.subject_type, a.subject_id): a for a in acks}
    for c in critics:
        a = by_key.get((c.kind, c.subject_type, c.subject_id))
        if a is None:
            continue
        c.acknowledged = True
        c.acknowledged_at = a.updated_at.isoformat() if a.updated_at else None
        c.acknowledged_by_email = (
            getattr(a.acknowledged_by, "email", None) if a.acknowledged_by_id else None
        )
        c.acknowledged_note = a.note or ""
    return critics


def severity_counts(critics: Iterable[Critic], *, only_unacknowledged: bool = True) -> dict:
    """Tally critics by severity. By default skips acknowledged ones — that's
    the count operators care about (the badge / list filter)."""
    counts = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 0, SEVERITY_INFO: 0}
    for c in critics:
        if only_unacknowledged and c.acknowledged:
            continue
        counts[c.severity] = counts.get(c.severity, 0) + 1
    return counts


def audit_critics_for_company(
    company,
    *,
    only_unacknowledged: bool = True,
    severity_in: tuple[str, ...] | None = None,
    invoice_ids: tuple[int, ...] | None = None,
    persist: bool = True,
) -> dict:
    """
    Sweep all (or a subset of) Invoices for a tenant and aggregate critic
    statistics. Used by:
        - the management command ``audit_invoice_critics``
        - the bulk-audit endpoint ``POST /api/invoices/audit-critics/``
    Optionally persists the latest counters back to ``Invoice.critics_count``
    so list views can filter without a re-scan.

    Args:
        only_unacknowledged: when True, acknowledged critics are excluded
            from per-invoice ``count`` and ``by_severity`` tallies but the
            full critic list still runs (so storage stays consistent).
        severity_in: filter the per-invoice ``items`` by severity (the
            aggregate counts always reflect the full unfiltered set).
        invoice_ids: limit sweep to these invoice ids (default: all of
            tenant's Invoices).
        persist: write critics_count and critics_count_by_severity back
            on each Invoice. Default True for the mgmt command path.

    Returns a JSON-serializable summary dict.
    """
    from billing.models import Invoice
    from collections import Counter
    from django.utils import timezone

    qs = Invoice.objects.filter(company=company)
    if invoice_ids:
        qs = qs.filter(id__in=list(invoice_ids))

    started = timezone.now()
    sev_totals = Counter()
    kind_totals = Counter()
    invoices_with_critics: list[dict] = []

    for inv in qs.iterator(chunk_size=100):
        critics = compute_critics_for_invoice(inv)
        annotate_acknowledgements(inv, critics)
        sev_counts = severity_counts(critics, only_unacknowledged=only_unacknowledged)
        unack_total = sum(sev_counts.values())

        if persist:
            new_count = unack_total
            new_by_sev = sev_counts
            if (inv.critics_count != new_count) or (
                inv.critics_count_by_severity != new_by_sev
            ):
                inv.critics_count = new_count
                inv.critics_count_by_severity = new_by_sev
                inv.save(update_fields=["critics_count", "critics_count_by_severity"])

        if unack_total == 0:
            continue
        for c in critics:
            if only_unacknowledged and c.acknowledged:
                continue
            sev_totals[c.severity] += 1
            kind_totals[c.kind] += 1

        # Surface filtered items in the response when requested
        if severity_in:
            shown = [
                c for c in critics
                if c.severity in severity_in and (not only_unacknowledged or not c.acknowledged)
            ]
        else:
            shown = [c for c in critics if not only_unacknowledged or not c.acknowledged]

        invoices_with_critics.append({
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "partner_id": inv.partner_id,
            "total_amount": str(inv.total_amount),
            "fiscal_status": inv.fiscal_status,
            "count": unack_total,
            "by_severity": sev_counts,
            "items": critics_to_dict(shown),
        })

    # Sort the per-invoice list: errors first, then by total count desc
    invoices_with_critics.sort(
        key=lambda r: (-r["by_severity"].get("error", 0), -r["count"]),
    )

    return {
        "started_at": started.isoformat(),
        "completed_at": timezone.now().isoformat(),
        "swept": qs.count(),
        "invoices_with_critics_count": len(invoices_with_critics),
        "by_severity": dict(sev_totals),
        "by_kind": dict(kind_totals),
        "results": invoices_with_critics,
    }
