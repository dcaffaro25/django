# -*- coding: utf-8 -*-
"""
NF ↔ Transaction matching service.

Read-only against accounting (Transaction, JournalEntry, BankTransaction).
Writes only to ``billing.NFTransactionLink``.

Pipeline:
    find_candidates(...) -> list[MatchResult]
    persist_links(matches, ...) -> dict (created / skipped / auto_accepted)
    rescan_for_nf(nota_fiscal) -> list[MatchResult]
    rescan_for_transaction(transaction) -> list[MatchResult]

Matching passes (per Tx, evaluated against the candidate set of NFs):
    1. nf_number == NotaFiscal.numero (exact)            +0.50
    2. cnpj ∈ {emit_cnpj, dest_cnpj}                     +0.25
    3. |tx.date - nf.data_emissao| ≤ window              +0.15
    4. |tx.amount - valor_nota| / valor_nota ≤ tolerance +0.10
    Fallback: regex-extract NF# from description / BankTransaction.description
              starts at 0.30 (instead of 0.50) before any add-on.
Confidence is clamped to [0, 1].

The service never mutates Transaction or JournalEntry.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from accounting.models import BankTransaction, Transaction
from billing.models import NFTransactionLink, NotaFiscal

logger = logging.getLogger(__name__)


# Heurística simples para extrair "NF 12345", "NFe 12345", "Nota 12345" etc.
_NF_NUMBER_REGEX = re.compile(
    r"\b(?:NF[-\s]?e?|NFe|Nota[-\s]Fiscal|Nota|N\.?\s?F\.?)[-\s:#nº]*0*(\d{1,9})\b",
    re.IGNORECASE,
)


def _digits_only(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


@dataclass
class MatchResult:
    """A single (tx, nf) candidate with its evidence."""
    transaction_id: int
    nota_fiscal_id: int
    confidence: Decimal
    method: str
    matched_fields: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "nota_fiscal_id": self.nota_fiscal_id,
            "confidence": str(self.confidence),
            "method": self.method,
            "matched_fields": list(self.matched_fields),
            "notes": self.notes,
        }


def _clamp_confidence(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0")
    if value > 1:
        return Decimal("1")
    return value.quantize(Decimal("0.001"))


def _score(
    tx: Transaction,
    nf: NotaFiscal,
    *,
    base: Decimal,
    method: str,
    cnpj_tx: str,
    matched_initial: list[str],
    date_window_days: int,
    amount_tolerance: Decimal,
) -> MatchResult:
    """Add the cnpj/date/amount evidence on top of a base score."""
    score = Decimal(base)
    matched = list(matched_initial)

    cnpj_emit = _digits_only(nf.emit_cnpj)
    cnpj_dest = _digits_only(nf.dest_cnpj)
    if cnpj_tx and cnpj_tx in {cnpj_emit, cnpj_dest}:
        score += Decimal("0.25")
        matched.append("cnpj")
    elif (
        cnpj_tx and len(cnpj_tx) == 14
        and (cnpj_tx[:8] == cnpj_emit[:8] or cnpj_tx[:8] == cnpj_dest[:8])
        and (cnpj_emit or cnpj_dest)
    ):
        # Matrix↔branch case: same legal entity (8-digit root), different
        # establishment. Common when the GL records the filial CNPJ but
        # the NF was issued from the matriz (or vice-versa).
        score += Decimal("0.20")
        matched.append("cnpj_root")
    elif cnpj_tx and (nf.emitente_id or nf.destinatario_id):
        # Alias fallback: the Tx's CNPJ may belong to an acquirer or
        # marketplace that the user has previously taught the system to
        # resolve to a real BP. If that BP is the NF's emitente or
        # destinatário, boost slightly less than cnpj_root.
        try:
            from billing.services.bp_alias_service import resolve_alias
            aliased_bp = resolve_alias(tx.company, cnpj_tx)
            if aliased_bp is not None and aliased_bp.id in (
                nf.emitente_id, nf.destinatario_id,
            ):
                score += Decimal("0.18")
                matched.append("cnpj_alias")
        except Exception:
            pass

    if tx.date and nf.data_emissao:
        try:
            delta = abs((tx.date - nf.data_emissao.date()).days)
            if delta <= date_window_days:
                score += Decimal("0.15")
                matched.append("date")
        except Exception:
            pass

    try:
        nf_val = Decimal(nf.valor_nota or 0)
        tx_val = Decimal(tx.amount or 0)
        if nf_val != 0:
            ratio = abs(tx_val - nf_val) / nf_val
            if ratio <= amount_tolerance:
                score += Decimal("0.10")
                matched.append("amount")
    except Exception:
        pass

    return MatchResult(
        transaction_id=tx.id,
        nota_fiscal_id=nf.id,
        confidence=_clamp_confidence(score),
        method=method,
        matched_fields=matched,
    )


def _candidates_by_nf_number(
    company,
    txs: Iterable[Transaction],
    *,
    date_window_days: int,
    amount_tolerance: Decimal,
) -> list[MatchResult]:
    """Pass 1: Transaction.nf_number == NotaFiscal.numero (exact)."""
    out: list[MatchResult] = []
    txs_with_nf = [t for t in txs if (t.nf_number or "").strip()]
    if not txs_with_nf:
        return out

    nf_numbers = {(t.nf_number or "").strip().lstrip("0") for t in txs_with_nf}
    nf_numbers.discard("")
    if not nf_numbers:
        return out

    # Match on numero ignoring leading zeros
    # NotaFiscal.numero is IntegerField — compare via int when possible.
    int_numbers = set()
    for raw in nf_numbers:
        try:
            int_numbers.add(int(raw))
        except (TypeError, ValueError):
            continue
    if not int_numbers:
        return out

    nfs = NotaFiscal.objects.filter(company=company, numero__in=int_numbers)
    nfs_by_numero: dict[int, list[NotaFiscal]] = {}
    for nf in nfs:
        nfs_by_numero.setdefault(nf.numero, []).append(nf)

    for tx in txs_with_nf:
        try:
            tx_num = int((tx.nf_number or "").strip())
        except (TypeError, ValueError):
            continue
        for nf in nfs_by_numero.get(tx_num, []):
            cnpj_tx = _digits_only(getattr(tx, "cnpj", "") or "")
            res = _score(
                tx, nf,
                base=Decimal("0.50"),
                method=NFTransactionLink.METHOD_NF_NUMBER,
                cnpj_tx=cnpj_tx,
                matched_initial=["nf_number"],
                date_window_days=date_window_days,
                amount_tolerance=amount_tolerance,
            )
            out.append(res)
    return out


def _candidates_from_description(
    company,
    txs: Iterable[Transaction],
    *,
    date_window_days: int,
    amount_tolerance: Decimal,
) -> list[MatchResult]:
    """Fallback pass: regex-extract NF number from Transaction.description."""
    out: list[MatchResult] = []
    extracted: list[tuple[Transaction, int]] = []
    for tx in txs:
        if (tx.nf_number or "").strip():
            continue  # already handled by nf_number pass
        desc = (getattr(tx, "description", "") or "")
        if not desc:
            continue
        m = _NF_NUMBER_REGEX.search(desc)
        if not m:
            continue
        try:
            extracted.append((tx, int(m.group(1))))
        except (TypeError, ValueError):
            continue
    if not extracted:
        return out

    int_numbers = {n for _, n in extracted}
    nfs = NotaFiscal.objects.filter(company=company, numero__in=int_numbers)
    nfs_by_numero: dict[int, list[NotaFiscal]] = {}
    for nf in nfs:
        nfs_by_numero.setdefault(nf.numero, []).append(nf)

    for tx, num in extracted:
        for nf in nfs_by_numero.get(num, []):
            cnpj_tx = _digits_only(getattr(tx, "cnpj", "") or "")
            res = _score(
                tx, nf,
                base=Decimal("0.30"),
                method=NFTransactionLink.METHOD_DESCRIPTION_REGEX,
                cnpj_tx=cnpj_tx,
                matched_initial=["description_regex"],
                date_window_days=date_window_days,
                amount_tolerance=amount_tolerance,
            )
            out.append(res)
    return out


def _candidates_from_bank_description(
    company,
    txs: Iterable[Transaction],
    *,
    date_window_days: int,
    amount_tolerance: Decimal,
) -> list[MatchResult]:
    """
    Sweep BankTransaction.description for NF numbers; match against the
    Transactions reconciled to that bank movement (via reverse FK if the
    project has it; otherwise we skip — BankTransaction lives on a separate
    model and its link to Transaction is reconciliation-flow-specific).
    Deliberately conservative: returns empty when no obvious join exists.
    """
    out: list[MatchResult] = []
    # Detect a "transactions" reverse manager on BankTransaction
    if not hasattr(BankTransaction, "transactions"):
        return out
    extracted_by_bank_id: dict[int, list[int]] = {}
    bts = BankTransaction.objects.filter(company=company).only(
        "id", "description", "cnpj"
    )
    for bt in bts:
        desc = bt.description or ""
        if not desc:
            continue
        nums: list[int] = []
        for m in _NF_NUMBER_REGEX.finditer(desc):
            try:
                nums.append(int(m.group(1)))
            except (TypeError, ValueError):
                continue
        if nums:
            extracted_by_bank_id[bt.id] = nums

    if not extracted_by_bank_id:
        return out

    all_numbers = {n for arr in extracted_by_bank_id.values() for n in arr}
    nfs = NotaFiscal.objects.filter(company=company, numero__in=all_numbers)
    nfs_by_numero: dict[int, list[NotaFiscal]] = {}
    for nf in nfs:
        nfs_by_numero.setdefault(nf.numero, []).append(nf)

    tx_ids = {t.id for t in txs}
    for bt_id, numbers in extracted_by_bank_id.items():
        try:
            bt = BankTransaction.objects.get(pk=bt_id)
            related_txs = list(bt.transactions.all())
        except Exception:
            continue
        for tx in related_txs:
            if tx.id not in tx_ids:
                continue
            for num in numbers:
                for nf in nfs_by_numero.get(num, []):
                    cnpj_tx = _digits_only(getattr(tx, "cnpj", "") or "")
                    res = _score(
                        tx, nf,
                        base=Decimal("0.25"),
                        method=NFTransactionLink.METHOD_BANK_DESCRIPTION,
                        cnpj_tx=cnpj_tx,
                        matched_initial=["bank_description"],
                        date_window_days=date_window_days,
                        amount_tolerance=amount_tolerance,
                    )
                    out.append(res)
    return out


def _dedupe(results: Iterable[MatchResult]) -> list[MatchResult]:
    """Keep the highest-confidence result per (tx, nf) pair."""
    by_pair: dict[tuple[int, int], MatchResult] = {}
    for r in results:
        key = (r.transaction_id, r.nota_fiscal_id)
        prev = by_pair.get(key)
        if prev is None or r.confidence > prev.confidence:
            by_pair[key] = r
    return list(by_pair.values())


def find_candidates(
    company,
    *,
    transaction_ids: Optional[Iterable[int]] = None,
    nota_fiscal_ids: Optional[Iterable[int]] = None,
    date_window_days: int = 7,
    amount_tolerance: Decimal = Decimal("0.01"),
    min_confidence: Decimal = Decimal("0.5"),
    limit: Optional[int] = None,
) -> list[MatchResult]:
    """
    Build a list of (transaction, nota_fiscal) candidate matches for ``company``.

    Args:
        transaction_ids: when provided, restrict the Tx side to these IDs.
            Useful for `rescan_for_transaction`. None scans all unlinked Txs
            (those without an ``accepted`` NFTransactionLink).
        nota_fiscal_ids: same on the NF side.
        date_window_days: tolerance in days between Tx.date and NF.data_emissao.
        amount_tolerance: proportional tolerance for amount match (0.01 = 1%).
        min_confidence: drop results below this score.
        limit: hard cap on returned results (after dedup + sort by confidence).
    """
    qs = Transaction.objects.filter(company=company)
    if transaction_ids is not None:
        qs = qs.filter(id__in=list(transaction_ids))
    else:
        # Skip Tx already with an accepted link
        accepted_tx_ids = NFTransactionLink.objects.filter(
            company=company,
            review_status=NFTransactionLink.REVIEW_ACCEPTED,
        ).values_list("transaction_id", flat=True)
        qs = qs.exclude(id__in=list(accepted_tx_ids))
    txs = list(qs.only("id", "nf_number", "cnpj", "date", "amount", "description"))

    results: list[MatchResult] = []
    results.extend(
        _candidates_by_nf_number(
            company, txs,
            date_window_days=date_window_days,
            amount_tolerance=amount_tolerance,
        )
    )
    results.extend(
        _candidates_from_description(
            company, txs,
            date_window_days=date_window_days,
            amount_tolerance=amount_tolerance,
        )
    )
    results.extend(
        _candidates_from_bank_description(
            company, txs,
            date_window_days=date_window_days,
            amount_tolerance=amount_tolerance,
        )
    )

    if nota_fiscal_ids is not None:
        wanted = set(nota_fiscal_ids)
        results = [r for r in results if r.nota_fiscal_id in wanted]

    results = _dedupe(results)
    results = [r for r in results if r.confidence >= min_confidence]
    results.sort(key=lambda r: r.confidence, reverse=True)
    if limit:
        results = results[:limit]
    return results


def persist_links(
    company,
    matches: Iterable[MatchResult],
    *,
    auto_accept_above: Decimal = Decimal("1.001"),
    dry_run: bool = False,
    bump_cache: bool = True,
) -> dict:
    """
    Persist match results as ``NFTransactionLink`` rows.

    Idempotent: existing rows for (tx, nf) keep their review_status; we update
    confidence/method/matched_fields/snapshots only when the new candidate has
    HIGHER confidence than the stored one AND the row is still ``suggested``.
    Accepted/rejected rows are never overwritten by automatic passes.

    Args:
        auto_accept_above: confidence threshold for auto-acceptance. Default
            1.001 means "never auto-accept" — the operator must review.
        dry_run: simulate without writing.
        bump_cache: invalidate report_cache when any new accepted row lands.
    """
    counters = {
        "created": 0,
        "updated": 0,
        "skipped_existing_protected": 0,
        "auto_accepted": 0,
    }
    bumped = False

    matches = list(matches)
    if not matches:
        return counters

    # Index existing rows for the affected pairs to dedup with one query
    pairs = {(m.transaction_id, m.nota_fiscal_id) for m in matches}
    tx_ids = {t for t, _ in pairs}
    nf_ids = {n for _, n in pairs}
    existing = {
        (r.transaction_id, r.nota_fiscal_id): r
        for r in NFTransactionLink.objects.filter(
            company=company,
            transaction_id__in=tx_ids,
            nota_fiscal_id__in=nf_ids,
        )
    }

    # Snapshot helpers
    tx_amounts = {
        t.id: t.amount
        for t in Transaction.objects.filter(company=company, id__in=tx_ids).only("id", "amount")
    }
    nf_valors = {
        n.id: n.valor_nota
        for n in NotaFiscal.objects.filter(company=company, id__in=nf_ids).only("id", "valor_nota")
    }

    if dry_run:
        # Counters only — do not write
        for m in matches:
            existing_row = existing.get((m.transaction_id, m.nota_fiscal_id))
            if existing_row is None:
                counters["created"] += 1
                if m.confidence >= auto_accept_above:
                    counters["auto_accepted"] += 1
            elif existing_row.review_status == NFTransactionLink.REVIEW_SUGGESTED:
                if m.confidence > Decimal(existing_row.confidence):
                    counters["updated"] += 1
            else:
                counters["skipped_existing_protected"] += 1
        return counters

    with db_transaction.atomic():
        for m in matches:
            key = (m.transaction_id, m.nota_fiscal_id)
            row = existing.get(key)
            tx_amt = tx_amounts.get(m.transaction_id)
            nf_val = nf_valors.get(m.nota_fiscal_id)

            if row is None:
                review_status = NFTransactionLink.REVIEW_SUGGESTED
                reviewed_at = None
                if m.confidence >= auto_accept_above:
                    review_status = NFTransactionLink.REVIEW_ACCEPTED
                    reviewed_at = timezone.now()
                    counters["auto_accepted"] += 1
                NFTransactionLink.objects.create(
                    company=company,
                    transaction_id=m.transaction_id,
                    nota_fiscal_id=m.nota_fiscal_id,
                    confidence=m.confidence,
                    method=m.method,
                    matched_fields=list(m.matched_fields),
                    review_status=review_status,
                    reviewed_at=reviewed_at,
                    tx_amount_snapshot=tx_amt,
                    nf_valor_snapshot=nf_val,
                    notes=m.notes,
                )
                counters["created"] += 1
                if review_status == NFTransactionLink.REVIEW_ACCEPTED:
                    bumped = True
                continue

            if row.review_status != NFTransactionLink.REVIEW_SUGGESTED:
                counters["skipped_existing_protected"] += 1
                continue

            # Update only when new evidence is strictly stronger
            if m.confidence > Decimal(row.confidence):
                row.confidence = m.confidence
                row.method = m.method
                row.matched_fields = list(m.matched_fields)
                row.tx_amount_snapshot = tx_amt
                row.nf_valor_snapshot = nf_val
                if m.confidence >= auto_accept_above:
                    row.review_status = NFTransactionLink.REVIEW_ACCEPTED
                    row.reviewed_at = timezone.now()
                    counters["auto_accepted"] += 1
                    bumped = True
                row.save()
                counters["updated"] += 1

    if bump_cache and bumped:
        try:
            from accounting.services.report_cache import bump_version
            bump_version(company.id)
        except Exception:
            logger.exception("nf_link_service: bump_version failed for company_id=%s", company.id)

    return counters


def accept_link(link: NFTransactionLink, *, user=None, notes: str = "") -> NFTransactionLink:
    """Mark a single link as accepted. Idempotent.

    Beyond marking the link itself, an accepted NF↔Tx link is a strong
    signal that the Tx's counterparty (CNPJ on the bank/book side) and
    the NF's counterparty (CNPJ on the fiscal side) are the same
    economic actor. When the two resolve to *different* BPs, suggest a
    BusinessPartnerGroup membership so future reports can consolidate
    them. The suggestion call is best-effort — never breaks accept.
    """
    if link.review_status == NFTransactionLink.REVIEW_ACCEPTED:
        return link
    link.review_status = NFTransactionLink.REVIEW_ACCEPTED
    link.reviewed_by = user
    link.reviewed_at = timezone.now()
    if notes:
        link.notes = (link.notes + "\n" + notes).strip() if link.notes else notes
    link.save()
    try:
        from accounting.services.report_cache import bump_version
        bump_version(link.company_id)
    except Exception:
        logger.exception("nf_link_service: bump_version failed for company_id=%s", link.company_id)
    try:
        _suggest_group_from_accepted_link(link)
    except Exception:
        logger.exception(
            "nf_link_service: bp_group suggest failed for link_id=%s", link.id,
        )
    return link


def _suggest_group_from_accepted_link(link: NFTransactionLink) -> None:
    """Resolve both sides of an accepted link to BPs and suggest grouping.

    Tx side: ``Transaction.cnpj`` → BP via identifier (with cnpj_root
    fallback inside ``resolve_bp_by_cnpj``).
    NF side: ``_resolve_partner_for_nf`` already drops self-CNPJ, so it
    returns the actual counterparty BP.
    """
    from billing.services.bp_group_service import (
        resolve_bp_by_cnpj, upsert_membership_suggestion,
    )
    from billing.services.nf_invoice_sync import _resolve_partner_for_nf

    tx = link.transaction
    nf = link.nota_fiscal
    if not tx or not nf:
        return
    bp_tx = resolve_bp_by_cnpj(tx.company, getattr(tx, "cnpj", None))
    bp_nf = _resolve_partner_for_nf(nf)
    if bp_tx is None or bp_nf is None or bp_tx.id == bp_nf.id:
        return
    upsert_membership_suggestion(
        bp_tx, bp_nf,
        method="nf_tx_link",
        source_id=link.id,
        confidence=link.confidence,
    )


def reject_link(link: NFTransactionLink, *, user=None, notes: str = "") -> NFTransactionLink:
    """Mark a link as rejected. Idempotent."""
    if link.review_status == NFTransactionLink.REVIEW_REJECTED:
        return link
    link.review_status = NFTransactionLink.REVIEW_REJECTED
    link.reviewed_by = user
    link.reviewed_at = timezone.now()
    if notes:
        link.notes = (link.notes + "\n" + notes).strip() if link.notes else notes
    link.save()
    return link


def rescan_for_nf(nota_fiscal: NotaFiscal, **kwargs) -> dict:
    """Cheap incremental scan when a single NF lands. Returns counters dict."""
    matches = find_candidates(
        nota_fiscal.company,
        nota_fiscal_ids=[nota_fiscal.id],
        **kwargs,
    )
    return persist_links(nota_fiscal.company, matches)


def rescan_for_transaction(tx: Transaction, **kwargs) -> dict:
    """Cheap incremental scan when a Tx is created/updated. Returns counters dict."""
    matches = find_candidates(
        tx.company,
        transaction_ids=[tx.id],
        **kwargs,
    )
    return persist_links(tx.company, matches)
