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
from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from billing.models import BusinessPartner, BusinessPartnerAlias

logger = logging.getLogger(__name__)


ALIAS_AUTO_PROMOTE_THRESHOLD = 5


def _digits(value) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


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
