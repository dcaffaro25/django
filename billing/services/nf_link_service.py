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

# "Parcela 2/3" / "01/02" / "002/003" embedded in the Tx description --
# the standard Brazilian way of tagging installment payments. When
# present, the expected per-Tx amount is ``nf.valor_nota / total``, not
# the full total. Real-world tags zero-pad to 3 digits ("002/003"), so
# we accept up to 3-digit parts; the ``_PARCELA_MAX`` gate then keeps
# implausible pairs out (typical retail caps at 12x; "143/949" would
# parse to 143 ≤ 949 but be rejected because 143 > 12). The
# ``(?<!\d)`` / ``(?!\d)`` lookarounds ensure we don't pick up the X/Y
# sub-string of a longer doc number.
_PARCELA_RE = re.compile(r"(?<!\d)(\d{1,3})\s*/\s*(\d{1,3})(?!\d)")
_PARCELA_MAX = 12


def _expected_tx_sign(nf: NotaFiscal) -> int:
    """Return the sign Transaction.amount should have to be consistent
    with this NF. Saída (tipo_operacao=1) → money in (+1); Entrada
    (=0) → money out (-1). Devolução (finalidade=4) inverts both:
    a return on a Saída refunds the customer (-1), and a return on
    an Entrada gets money back from the vendor (+1)."""
    base = +1 if (nf.tipo_operacao == 1) else -1
    if nf.finalidade == 4:
        base = -base
    return base


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
        boosted = False
        try:
            from billing.services.bp_alias_service import resolve_alias
            aliased_bp = resolve_alias(tx.company, cnpj_tx)
            if aliased_bp is not None and aliased_bp.id in (
                nf.emitente_id, nf.destinatario_id,
            ):
                score += Decimal("0.18")
                matched.append("cnpj_alias")
                boosted = True
        except Exception:
            pass
        # Group fallback: even with no alias, the Tx's CNPJ might
        # resolve to a BP that shares an accepted Group with the NF's
        # counterparty (cross-root consolidation: CPF↔CNPJ, holding
        # company, etc.). Catches what cnpj_root + alias don't.
        if not boosted:
            try:
                from billing.services.bp_group_service import (
                    find_shared_group, resolve_bp_by_cnpj,
                )
                bp_tx = resolve_bp_by_cnpj(tx.company, cnpj_tx)
                if bp_tx is not None:
                    nf_bp_id = nf.emitente_id or nf.destinatario_id
                    nf_bp = nf.emitente if nf.emitente_id else nf.destinatario
                    shared = find_shared_group(bp_tx, nf_bp)
                    if shared is not None:
                        score += Decimal("0.22")
                        matched.append("cnpj_group")
            except Exception:
                pass
    elif (not cnpj_tx) and (nf.emitente_id or nf.destinatario_id):
        # Name-alias fallback: the Tx side has no CNPJ at all (foreign
        # customer, informal PIX, e-commerce gateway settlement). The
        # only counterparty signal is in tx.description; if any of the
        # extracted name tokens has been learned (via accepted prior
        # NF↔Tx links) to resolve to the NF's emitente or destinatario,
        # boost the score. ``+0.18`` mirrors cnpj_alias because the
        # learned-evidence quality is the same.
        try:
            from billing.services.bp_alias_service import (
                _extract_name_tokens, resolve_name_alias,
            )
            nf_partner_ids = {nf.emitente_id, nf.destinatario_id}
            nf_partner_ids.discard(None)
            for tok in _extract_name_tokens(getattr(tx, "description", "") or ""):
                aliased_bp = resolve_name_alias(tx.company, tok)
                if aliased_bp is not None and aliased_bp.id in nf_partner_ids:
                    score += Decimal("0.18")
                    matched.append("name_alias")
                    break
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
            ratio = abs(tx_val - nf_val) / abs(nf_val)
            if ratio <= amount_tolerance:
                score += Decimal("0.10")
                matched.append("amount")
            else:
                # Parcela detection -- when the Tx description carries
                # an "X/Y" tag, we treat ``nf.valor_nota / Y`` as the
                # expected per-Tx amount and grade against that. Catches
                # the dominant Brazilian installment-payment case where
                # one NF is settled by N Txs of value/N each, which the
                # plain full-amount comparison flagged as a 50-67%
                # mismatch. ``parcela_X/Y`` lands in matched_fields so
                # the UI / audit can see how the score was built.
                desc = getattr(tx, "description", "") or ""
                # Pick the FIRST plausible X/Y pair: 1 ≤ part ≤ total ≤
                # PARCELA_MAX. Earlier matches with implausible values
                # (e.g. doc numbers) get skipped without falling back.
                m = None
                for cand in _PARCELA_RE.finditer(desc):
                    try:
                        p = int(cand.group(1))
                        t = int(cand.group(2))
                    except (TypeError, ValueError):
                        continue
                    if 1 <= p <= t <= _PARCELA_MAX:
                        m = (p, t)
                        break
                if m is not None:
                    part, total = m
                    expected_per = nf_val / total
                    if expected_per != 0:
                        ratio_p = abs(tx_val - expected_per) / abs(expected_per)
                        if ratio_p <= amount_tolerance:
                            score += Decimal("0.10")
                            matched.append(f"parcela_{part}/{total}")
    except Exception:
        pass

    # Sign-mismatch guard: a Saída NF (we sold) should match a positive
    # Tx (money in). A negative Tx against a Saída NF is almost
    # certainly a chargeback / fee reversal that the matcher snared on
    # nf_number alone. Zero out the candidate so it falls below the
    # default min_confidence and disappears from the suggested queue.
    # Devolução (finalidade=4) inverts the expected sign and is handled
    # by ``_expected_tx_sign``.
    try:
        tx_val_check = Decimal(tx.amount or 0)
        if tx_val_check != 0 and Decimal(nf.valor_nota or 0) != 0:
            expected_sign = _expected_tx_sign(nf)
            actual_sign = +1 if tx_val_check > 0 else -1
            if expected_sign != actual_sign:
                return MatchResult(
                    transaction_id=tx.id,
                    nota_fiscal_id=nf.id,
                    confidence=Decimal("0"),
                    method=method,
                    matched_fields=list(matched) + ["sign_mismatch"],
                    notes="Tx sign does not match NF tipo_operacao/finalidade",
                )
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


def accept_link(
    link: NFTransactionLink,
    *,
    user=None,
    notes: str = "",
    allocated_amount: Optional[Decimal] = None,
) -> NFTransactionLink:
    """Mark a single link as accepted. Idempotent.

    Beyond marking the link itself, an accepted NF↔Tx link is a strong
    signal that the Tx's counterparty (CNPJ on the bank/book side) and
    the NF's counterparty (CNPJ on the fiscal side) are the same
    economic actor. When the two resolve to *different* BPs, suggest a
    BusinessPartnerGroup membership so future reports can consolidate
    them. The suggestion call is best-effort — never breaks accept.

    When the link is a **parcela** (matched_fields contains
    ``parcela_X/Y``) and ``allocated_amount`` isn't supplied, we fill
    it with ``|tx.amount|`` so the audit trail records that this Tx
    covers exactly its own slice of ``nf.valor_nota``. Caller-supplied
    ``allocated_amount`` always wins.
    """
    if link.review_status == NFTransactionLink.REVIEW_ACCEPTED:
        return link
    link.review_status = NFTransactionLink.REVIEW_ACCEPTED
    link.reviewed_by = user
    link.reviewed_at = timezone.now()
    if allocated_amount is not None:
        try:
            link.allocated_amount = Decimal(allocated_amount)
        except Exception:
            pass
    elif link.allocated_amount is None:
        # Auto-fill for parcelas only -- a one-shot full match doesn't
        # need allocated_amount (NF total = Tx amount = full coverage).
        is_parcela = any(
            isinstance(t, str) and t.startswith("parcela_")
            for t in (link.matched_fields or [])
        )
        if is_parcela:
            tx = link.transaction
            tx_amt = getattr(tx, "amount", None) if tx else None
            if tx_amt is not None:
                try:
                    link.allocated_amount = abs(Decimal(tx_amt))
                except Exception:
                    pass
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
    # Name-alias learning: when the Tx side has no CNPJ, the
    # group-suggestion hook above silently exits (resolve_bp_by_cnpj
    # returns None for an empty string). The Tx description carries
    # the only signal we have for the counterparty in that case --
    # capture it as a name alias so the next no-CNPJ Tx with similar
    # description tokens auto-resolves.
    try:
        from billing.services.bp_alias_service import suggest_name_aliases_from_link
        suggest_name_aliases_from_link(link)
    except Exception:
        logger.exception(
            "nf_link_service: name-alias suggest failed for link_id=%s", link.id,
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


def audit_suggested_links(
    company,
    *,
    date_window_days: int = 7,
    amount_tolerance: Decimal = Decimal("0.01"),
    min_confidence: Decimal = Decimal("0.5"),
    dry_run: bool = False,
) -> dict:
    """Re-score every ``suggested`` link for ``company`` against the
    current scoring logic. Three outcomes per row:

      * **rejected (sign_mismatch)** -- the new score returns 0 because
        Tx.amount sign disagrees with the NF tipo_operacao/finalidade
        (chargebacks, fee reversals snared on nf_number alone).
      * **rejected (below_min_confidence)** -- new score < min_confidence
        and the row carries no protected status. Catches stale matches
        where the underlying Tx or NF data has shifted enough to
        invalidate the original suggestion.
      * **updated** -- new score is HIGHER than the stored one (e.g.
        the parcela detector kicked in and added +0.10 / a new dimension
        was matched). Updates ``confidence`` and ``matched_fields``.

    Used by ``rescan_nf_links --audit-existing`` to clean up the
    suggested queue after a scoring change without scanning fresh
    candidates. Read-only against accounting; only writes to
    ``NFTransactionLink``.
    """
    counters = {
        "scanned": 0,
        "rejected_sign_mismatch": 0,
        "rejected_low_confidence": 0,
        "updated_higher": 0,
        "unchanged": 0,
    }

    qs = (
        NFTransactionLink.objects
        .filter(company=company, review_status=NFTransactionLink.REVIEW_SUGGESTED)
        .select_related("nota_fiscal", "transaction")
    )
    rows = list(qs)
    counters["scanned"] = len(rows)
    if not rows:
        return counters

    bumped = False
    with db_transaction.atomic():
        for row in rows:
            tx = row.transaction
            nf = row.nota_fiscal
            if tx is None or nf is None:
                continue
            cnpj_tx = _digits_only(getattr(tx, "cnpj", "") or "")
            base = (
                Decimal("0.50")
                if row.method == NFTransactionLink.METHOD_NF_NUMBER
                else Decimal("0.30")
                if row.method == NFTransactionLink.METHOD_DESCRIPTION_REGEX
                else Decimal("0.25")
            )
            initial = [row.method] if row.method else []
            new = _score(
                tx, nf,
                base=base,
                method=row.method or NFTransactionLink.METHOD_NF_NUMBER,
                cnpj_tx=cnpj_tx,
                matched_initial=initial,
                date_window_days=date_window_days,
                amount_tolerance=amount_tolerance,
            )
            new_conf = Decimal(new.confidence)
            old_conf = Decimal(row.confidence)
            sign_bad = "sign_mismatch" in (new.matched_fields or [])

            if sign_bad:
                counters["rejected_sign_mismatch"] += 1
                if not dry_run:
                    row.review_status = NFTransactionLink.REVIEW_REJECTED
                    row.reviewed_at = timezone.now()
                    row.notes = (
                        (row.notes + "\n" if row.notes else "")
                        + "Auto-rejected: Tx sign does not match NF tipo_operacao/finalidade."
                    )
                    row.matched_fields = list(new.matched_fields)
                    row.save()
                continue

            if new_conf < min_confidence:
                counters["rejected_low_confidence"] += 1
                if not dry_run:
                    row.review_status = NFTransactionLink.REVIEW_REJECTED
                    row.reviewed_at = timezone.now()
                    row.notes = (
                        (row.notes + "\n" if row.notes else "")
                        + f"Auto-rejected: new score {new_conf} < min_confidence {min_confidence}."
                    )
                    row.confidence = new_conf
                    row.matched_fields = list(new.matched_fields)
                    row.save()
                continue

            if new_conf > old_conf or set(new.matched_fields or []) != set(row.matched_fields or []):
                counters["updated_higher"] += 1
                if not dry_run:
                    row.confidence = new_conf
                    row.matched_fields = list(new.matched_fields)
                    row.save()
            else:
                counters["unchanged"] += 1

    if not dry_run and (counters["rejected_sign_mismatch"] or counters["rejected_low_confidence"]):
        bumped = True

    if bumped:
        try:
            from accounting.services.report_cache import bump_version
            bump_version(company.id)
        except Exception:
            logger.exception("nf_link_service: bump_version failed for company_id=%s", company.id)

    return counters


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
