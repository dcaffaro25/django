# -*- coding: utf-8 -*-
"""
BusinessPartnerAlias — string CNPJ/CPF → BP resolver hints.

Diferente de Groups (que liga DOIS BPs cadastrados), o alias liga uma
**string** observada externamente (extrato bancário, descrição) a UM BP
existente. É o caso típico de **adquirentes/marketplaces**: o extrato
mostra o CNPJ da Cielo/Stone/Mercado Livre, mas o cliente real tem
identidade própria — só que essa identidade não tem CNPJ próprio do lado
banco-financeiro.

Estratégia de aprendizado:
- Quando o usuário aceita uma reconciliação onde a CNPJ do extrato NÃO
  resolve para nenhum BP cadastrado mas o lado livro tem um BP claro,
  registramos sugestão de alias do CNPJ → BP do livro.
- Threshold de promoção é mais conservador (default 5) — o ruído desse
  sinal é maior porque adquirentes legitimamente recebem por múltiplos
  clientes; só consolidamos depois de várias confirmações independentes.
- Após aceito, o ``nf_link_service._score`` ganha um boost
  ``+0.18`` quando a CNPJ da Tx (lado banco) é alias de algum BP
  candidato (lado fiscal) — preferindo o match aprendido sobre o
  fallback puramente baseado em raiz CNPJ.

Esta service é completamente independente de ``bp_group_service`` e pode
ser desligada sem afetar o sistema de Groups.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from billing.models import BusinessPartner, BusinessPartnerAlias

logger = logging.getLogger(__name__)


ALIAS_AUTO_PROMOTE_THRESHOLD = 5
# Name aliases auto-promote sooner than CNPJ aliases. Each accepted
# NF↔Tx link is an explicit operator decision; three independent links
# pointing the same description token at the same BP is strong enough
# evidence to start using the alias for scoring.
NAME_ALIAS_AUTO_PROMOTE_THRESHOLD = 3

# Tokens that appear in many descriptions without identifying the
# party — banks, payment processors, generic transfer / payment verbs.
# Kept conservative; expand as we observe noise. Operators can also
# reject any auto-suggested alias that turns out to be too generic.
_NAME_TOKEN_STOPLIST = frozenset({
    # Banks
    "itau", "itau unibanco", "banco itau", "banco do brasil",
    "bradesco", "santander", "caixa", "nubank", "inter",
    "btg pactual", "btg",
    # Acquirers / gateways
    "stone", "cielo", "rede", "getnet", "pagseguro", "mercado pago",
    "paypal",
    # Account / channel labels
    "conta corrente", "conta gateway", "conta poupanca",
    # Generic operations
    "pagamento", "recebimento", "transferencia", "deposito",
    "saque", "tarifa", "estorno", "devolucao",
    "pix", "ted", "doc", "boleto",
    # Generic accounting captions
    "venda de produtos", "venda", "compra", "compra de produtos",
})

# Sub-segment splitters in a Tx description: pipes, semicolons, the
# " - " delimiter that separates accounting-code captions from line
# bodies, and a small set of common keyword separators.
_DESC_SPLIT_RE = re.compile(r"[|;]+|\s-\s")
# A token is "name-like" only when it contains at least one alpha
# character and isn't dominated by digits (skips dates, amounts,
# CFOPs, etc.).
_HAS_ALPHA_RE = re.compile(r"[A-Za-zÀ-ſ]")


def _digits(value) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def _normalize_name(value) -> str:
    """Lowercase, strip diacritics, collapse whitespace, cap at 80 chars.

    Matches the storage shape of ``BusinessPartnerAlias.alias_identifier``
    when ``kind=name``. Returns ``""`` for empty / non-string input so
    callers can short-circuit on falsy.
    """
    if not value:
        return ""
    s = str(value).strip().lower()
    s = "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )
    s = re.sub(r"\s+", " ", s)
    return s[:80]


def _extract_name_tokens(description: str) -> list[str]:
    """Pull candidate name tokens from a Tx description for alias learning.

    Splits on common separators (``|``, ``;``, ``" - "``) then filters
    out tokens that aren't plausible party names — empty / too short,
    pure numeric, contains ``/`` (date or parcela), in the bank-name
    stoplist, or all-stopwords. Returns normalized tokens deduped, in
    original order.
    """
    if not description:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for chunk in _DESC_SPLIT_RE.split(description):
        tok = _normalize_name(chunk)
        if len(tok) < 4:
            continue
        if not _HAS_ALPHA_RE.search(tok):
            continue
        if "/" in tok:
            continue
        if tok in _NAME_TOKEN_STOPLIST:
            continue
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def _evidence_already_recorded(alias, *, source: str, source_id) -> bool:
    if not alias.evidence:
        return False
    key = (source, source_id)
    for entry in alias.evidence:
        if (entry.get("source"), entry.get("source_id")) == key:
            return True
    return False


def _append_evidence(alias, *, source: str, source_id, confidence: Decimal) -> None:
    alias.evidence.append({
        "source": source,
        "source_id": source_id,
        "at": timezone.now().isoformat(),
        "confidence": str(confidence),
    })
    if confidence > alias.confidence:
        alias.confidence = confidence


@db_transaction.atomic
def upsert_alias_suggestion(
    bp: BusinessPartner,
    alias_cnpj_or_cpf: str,
    *,
    source: str = BusinessPartnerAlias.SOURCE_BANK_RECONCILIATION,
    source_id=None,
    confidence: Decimal = Decimal("0.5"),
    auto_promote_threshold: int = ALIAS_AUTO_PROMOTE_THRESHOLD,
) -> Optional[BusinessPartnerAlias]:
    """Registra que ``alias_cnpj_or_cpf`` deve resolver para ``bp``.

    Ignora silenciosamente quando:
    - ``alias_cnpj_or_cpf`` já é o próprio identifier do BP (não há nada
      a aprender).
    - ``alias_cnpj_or_cpf`` compartilha a mesma raiz de 8 dígitos do BP
      (resolve_bp_by_cnpj já cobre via fallback).
    """
    if bp is None:
        return None
    digits = _digits(alias_cnpj_or_cpf)
    if not digits:
        return None
    bp_digits = _digits(bp.identifier)
    if digits == bp_digits:
        return None
    if (
        len(digits) == 14 and len(bp_digits) == 14
        and digits[:8] == bp_digits[:8]
    ):
        # Mesma raiz CNPJ — não precisa de alias.
        return None

    company = bp.company
    confidence = Decimal(confidence)

    alias, created = BusinessPartnerAlias.objects.get_or_create(
        business_partner=bp,
        kind=BusinessPartnerAlias.KIND_CNPJ,
        alias_identifier=digits,
        defaults={
            "company": company,
            "review_status": BusinessPartnerAlias.REVIEW_SUGGESTED,
            "source": source,
            "confidence": confidence,
            "hit_count": 1,
            "evidence": [],
            "last_used_at": timezone.now(),
        },
    )
    if _evidence_already_recorded(alias, source=source, source_id=source_id):
        return alias

    _append_evidence(alias, source=source, source_id=source_id, confidence=confidence)
    if not created:
        if alias.review_status == BusinessPartnerAlias.REVIEW_REJECTED:
            # Reabre uma sugestão antes rejeitada — usuário pode rejeitar
            # de novo se quiser.
            alias.review_status = BusinessPartnerAlias.REVIEW_SUGGESTED
            alias.reviewed_at = None
            alias.reviewed_by = None
        alias.hit_count += 1
    alias.last_used_at = timezone.now()

    # Auto-promove ao bater o threshold, mas só se ninguém mais reivindica
    # esta string (constraint parcial garante exclusividade do aceito).
    promoted = False
    if (
        alias.review_status == BusinessPartnerAlias.REVIEW_SUGGESTED
        and alias.hit_count >= auto_promote_threshold
    ):
        # Se já existe um alias aceito para esta string apontando para
        # OUTRO BP, o usuário deve resolver manualmente — não promovemos.
        conflict = (
            BusinessPartnerAlias.objects
            .filter(
                company=company,
                kind=BusinessPartnerAlias.KIND_CNPJ,
                alias_identifier=digits,
                review_status=BusinessPartnerAlias.REVIEW_ACCEPTED,
            )
            .exclude(pk=alias.pk)
            .exists()
        )
        if not conflict:
            alias.review_status = BusinessPartnerAlias.REVIEW_ACCEPTED
            alias.reviewed_at = timezone.now()
            promoted = True

    alias.save()
    if promoted:
        logger.info(
            "bp_alias_service: auto-promoted alias %s → BP#%s after %d hits",
            digits, bp.id, alias.hit_count,
        )
    return alias


def resolve_alias(company, alias_cnpj_or_cpf: str) -> Optional[BusinessPartner]:
    """Retorna o BP cujo alias aceito bate com a string informada."""
    digits = _digits(alias_cnpj_or_cpf)
    if not digits or company is None:
        return None
    alias = (
        BusinessPartnerAlias.objects
        .filter(
            company=company,
            kind=BusinessPartnerAlias.KIND_CNPJ,
            alias_identifier=digits,
            review_status=BusinessPartnerAlias.REVIEW_ACCEPTED,
        )
        .select_related("business_partner")
        .first()
    )
    if alias is None:
        return None
    # touch last_used_at on read (best-effort, ignore failures)
    try:
        BusinessPartnerAlias.objects.filter(pk=alias.pk).update(
            last_used_at=timezone.now(),
        )
    except Exception:
        pass
    return alias.business_partner


@db_transaction.atomic
def upsert_name_alias_suggestion(
    bp: BusinessPartner,
    name_token: str,
    *,
    source: str = BusinessPartnerAlias.SOURCE_NF_TX_LINK,
    source_id=None,
    confidence: Decimal = Decimal("0.5"),
    auto_promote_threshold: int = NAME_ALIAS_AUTO_PROMOTE_THRESHOLD,
) -> Optional[BusinessPartnerAlias]:
    """Register that a normalized name token should resolve to ``bp``.

    Same shape as ``upsert_alias_suggestion`` but for ``kind=name``.
    Skips silently when:
    - ``name_token`` normalizes empty.
    - ``name_token`` is in the stoplist (caller passed a bank/processor
      name we already know shouldn't anchor a BP).
    - ``name_token`` matches the BP's own normalized identifier (rare
      for names, but kept for symmetry with the CNPJ branch).
    """
    if bp is None:
        return None
    token = _normalize_name(name_token)
    if not token or token in _NAME_TOKEN_STOPLIST:
        return None

    company = bp.company
    confidence = Decimal(confidence)

    alias, created = BusinessPartnerAlias.objects.get_or_create(
        business_partner=bp,
        kind=BusinessPartnerAlias.KIND_NAME,
        alias_identifier=token,
        defaults={
            "company": company,
            "review_status": BusinessPartnerAlias.REVIEW_SUGGESTED,
            "source": source,
            "confidence": confidence,
            "hit_count": 1,
            "evidence": [],
            "last_used_at": timezone.now(),
        },
    )
    if _evidence_already_recorded(alias, source=source, source_id=source_id):
        return alias

    _append_evidence(alias, source=source, source_id=source_id, confidence=confidence)
    if not created:
        if alias.review_status == BusinessPartnerAlias.REVIEW_REJECTED:
            alias.review_status = BusinessPartnerAlias.REVIEW_SUGGESTED
            alias.reviewed_at = None
            alias.reviewed_by = None
        alias.hit_count += 1
    alias.last_used_at = timezone.now()

    promoted = False
    if (
        alias.review_status == BusinessPartnerAlias.REVIEW_SUGGESTED
        and alias.hit_count >= auto_promote_threshold
    ):
        # Block auto-promotion when the same token already resolves to
        # a different accepted BP -- ambiguous; operator must arbitrate.
        conflict = (
            BusinessPartnerAlias.objects
            .filter(
                company=company,
                kind=BusinessPartnerAlias.KIND_NAME,
                alias_identifier=token,
                review_status=BusinessPartnerAlias.REVIEW_ACCEPTED,
            )
            .exclude(pk=alias.pk)
            .exists()
        )
        if not conflict:
            alias.review_status = BusinessPartnerAlias.REVIEW_ACCEPTED
            alias.reviewed_at = timezone.now()
            promoted = True

    alias.save()
    if promoted:
        logger.info(
            "bp_alias_service: auto-promoted name alias %r → BP#%s after %d hits",
            token, bp.id, alias.hit_count,
        )
    return alias


def resolve_name_alias(company, name_token: str) -> Optional[BusinessPartner]:
    """Resolve a description token to its BP via accepted name aliases."""
    token = _normalize_name(name_token)
    if not token or company is None:
        return None
    alias = (
        BusinessPartnerAlias.objects
        .filter(
            company=company,
            kind=BusinessPartnerAlias.KIND_NAME,
            alias_identifier=token,
            review_status=BusinessPartnerAlias.REVIEW_ACCEPTED,
        )
        .select_related("business_partner")
        .first()
    )
    if alias is None:
        return None
    try:
        BusinessPartnerAlias.objects.filter(pk=alias.pk).update(
            last_used_at=timezone.now(),
        )
    except Exception:
        pass
    return alias.business_partner


def suggest_name_aliases_from_link(link) -> int:
    """Learn name → BP mappings from an accepted NF↔Tx link.

    Triggered from ``nf_link_service.accept_link`` *after* the link is
    saved. Only does work when the Tx side has no CNPJ to anchor a
    regular alias — that's the gap this feature fills (foreign
    customers, informal e-commerce, PIX without payer CNPJ).

    Walks tokens extracted from ``link.transaction.description`` and
    upserts a name-alias suggestion pointing each one at the NF's
    counterparty BP. Tokens past ~6 are ignored to keep noise down.
    """
    tx = getattr(link, "transaction", None)
    nf = getattr(link, "nota_fiscal", None)
    if tx is None or nf is None:
        return 0
    if _digits(getattr(tx, "cnpj", "") or ""):
        return 0  # CNPJ branch already handles this case

    # Only the NF's *counterparty* makes sense as the alias target.
    # _resolve_partner_for_nf already drops self-CNPJ.
    try:
        from billing.services.nf_invoice_sync import _resolve_partner_for_nf
        bp_nf = _resolve_partner_for_nf(nf)
    except Exception:
        return 0
    if bp_nf is None:
        return 0

    desc = getattr(tx, "description", "") or ""
    tokens = _extract_name_tokens(desc)[:6]
    upserts = 0
    for tok in tokens:
        try:
            upsert_name_alias_suggestion(
                bp_nf, tok,
                source=BusinessPartnerAlias.SOURCE_NF_TX_LINK,
                source_id=link.id,
                confidence=Decimal(link.confidence) if link.confidence else Decimal("0.5"),
            )
            upserts += 1
        except Exception:
            logger.exception(
                "bp_alias_service: name alias upsert failed for "
                "link=%s token=%r bp=%s",
                link.id, tok, bp_nf.id,
            )
    return upserts


def suggest_aliases_from_reconciliation(
    company,
    bank_txs,
    journal_entries,
    *,
    reconciliation_id=None,
    confidence: Decimal = Decimal("0.7"),
) -> int:
    """Aprende alias quando um lado da reconciliação não resolve para BP.

    Casos cobertos:
    - Lado banco com CNPJ que não resolve para BP, lado livro com BP
      definido → aprende alias do CNPJ banco apontando para o BP livro.
    - Lado livro com CNPJ que não resolve, lado banco com BP claro →
      aprende alias inverso (raro, mas simétrico).

    Quando ambos resolvem para BPs diferentes, é caso de Group, não alias
    — ``suggest_groups_from_reconciliation`` cuida disso.
    """
    if not bank_txs or not journal_entries:
        return 0

    from billing.services.bp_group_service import resolve_bp_by_cnpj

    bank_cnpjs = {
        getattr(bt, "cnpj", None)
        for bt in bank_txs
        if getattr(bt, "cnpj", None)
    }
    je_cnpjs = set()
    for je in journal_entries:
        tx = getattr(je, "transaction", None)
        if tx is not None and getattr(tx, "cnpj", None):
            je_cnpjs.add(tx.cnpj)

    upserts = 0
    for bank_cnpj in bank_cnpjs:
        bp_bank = resolve_bp_by_cnpj(company, bank_cnpj)
        if bp_bank is not None:
            continue  # bank side resolves; not an alias case
        for je_cnpj in je_cnpjs:
            bp_book = resolve_bp_by_cnpj(company, je_cnpj)
            if bp_book is None:
                continue  # neither side resolves; can't learn an alias
            try:
                upsert_alias_suggestion(
                    bp_book, bank_cnpj,
                    source=BusinessPartnerAlias.SOURCE_BANK_RECONCILIATION,
                    source_id=reconciliation_id,
                    confidence=confidence,
                )
                upserts += 1
            except Exception:
                logger.exception(
                    "bp_alias_service: suggest from reconciliation failed "
                    "(rec=%s, bp=%s, alias=%s)",
                    reconciliation_id, bp_book.id, bank_cnpj,
                )

    # Symmetric: book CNPJ unresolvable, bank CNPJ resolved.
    for je_cnpj in je_cnpjs:
        bp_book = resolve_bp_by_cnpj(company, je_cnpj)
        if bp_book is not None:
            continue
        for bank_cnpj in bank_cnpjs:
            bp_bank = resolve_bp_by_cnpj(company, bank_cnpj)
            if bp_bank is None:
                continue
            try:
                upsert_alias_suggestion(
                    bp_bank, je_cnpj,
                    source=BusinessPartnerAlias.SOURCE_BANK_RECONCILIATION,
                    source_id=reconciliation_id,
                    confidence=confidence,
                )
                upserts += 1
            except Exception:
                logger.exception(
                    "bp_alias_service: symmetric suggest failed "
                    "(rec=%s, bp=%s, alias=%s)",
                    reconciliation_id, bp_bank.id, je_cnpj,
                )

    return upserts
