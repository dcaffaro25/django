# -*- coding: utf-8 -*-
"""
BusinessPartnerGroup — populador de sugestões a partir de ações do usuário.

Quatro pontos de entrada usam ``upsert_membership_suggestion`` para registrar
que duas BPs distintas representam o mesmo ator econômico:

1. ``billing.services.nf_link_service.accept_link`` — o usuário aceitou um
   vínculo NF↔Tx em que a contraparte da Tx (CNPJ no extrato/livro) difere
   da contraparte da NF.
2. Reconciliação banco↔livro finalizada (``accounting.views``) — o CNPJ na
   linha bancária não bate com o BP da JE em que o usuário a casou.
3. ``billing.services.nf_invoice_sync.attach_invoice_to_nf`` — anexar uma
   Invoice cuja ``partner`` difere do parceiro resolvido na NF.
4. Edição manual de membership (UI).

Algoritmo (em ordem de checagem em ``upsert_membership_suggestion``):
- BPs iguais → no-op.
- Ambos já no mesmo Group aceito → atualiza evidence; nada mais a fazer.
- Nenhum em Group → cria Group novo, marca ``primary`` (BP mais antigo) como
  aceito estrutural e o outro como ``suggested`` com hit_count=1.
- Apenas um em Group G → adiciona o outro a G como ``suggested``.
- Em Groups diferentes → registra sugestão de **merge** com flag especial
  na evidence; nunca promove automaticamente — exige confirmação humana.

Promoção automática: ao bater ``hit_count >= AUTO_PROMOTE_THRESHOLD``
(default 3) sugestões não-merge viram ``accepted``. Sugestões conflitantes
para o mesmo BP em outros Groups são automaticamente rejeitadas na mesma
transaction (mantém invariante de "um BP em no máximo um Group ativo").

A função é reentrante e idempotente — chamadas repetidas com o mesmo
``(method, source_id)`` não inflam ``hit_count``.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from billing.models import (
    BusinessPartner,
    BusinessPartnerGroup,
    BusinessPartnerGroupMembership,
)

logger = logging.getLogger(__name__)


AUTO_PROMOTE_THRESHOLD = 3
EVIDENCE_KIND_NORMAL = "normal"
EVIDENCE_KIND_MERGE = "merge"


def _accepted_membership(bp: BusinessPartner) -> Optional[BusinessPartnerGroupMembership]:
    return (
        BusinessPartnerGroupMembership.objects
        .filter(
            business_partner=bp,
            review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
        )
        .select_related("group")
        .first()
    )


def _evidence_already_recorded(
    membership: BusinessPartnerGroupMembership,
    *,
    method: str,
    source_id,
) -> bool:
    """Idempotência: mesmo (method, source_id) já tem registro?"""
    if not membership.evidence:
        return False
    key = (method, source_id)
    for entry in membership.evidence:
        if (entry.get("method"), entry.get("source_id")) == key:
            return True
    return False


def _append_evidence(
    membership: BusinessPartnerGroupMembership,
    *,
    method: str,
    source_id,
    confidence: Decimal,
    kind: str = EVIDENCE_KIND_NORMAL,
) -> None:
    membership.evidence.append({
        "method": method,
        "source_id": source_id,
        "at": timezone.now().isoformat(),
        "confidence": str(confidence),
        "kind": kind,
    })
    if confidence > membership.confidence:
        membership.confidence = confidence


def _pick_primary(bp_a: BusinessPartner, bp_b: BusinessPartner) -> BusinessPartner:
    """BP com id mais baixo (mais antigo) vira primary — tiebreaker estável."""
    return bp_a if bp_a.id <= bp_b.id else bp_b


def _reject_conflicting_suggestions(bp: BusinessPartner, keep_group_id: int) -> None:
    """Quando um BP é aceito em Group X, sugestões dele em outros Groups
    deixam de ter sentido (invariante: um BP em no máximo um Group)."""
    (
        BusinessPartnerGroupMembership.objects
        .filter(
            business_partner=bp,
            review_status=BusinessPartnerGroupMembership.REVIEW_SUGGESTED,
        )
        .exclude(group_id=keep_group_id)
        .update(
            review_status=BusinessPartnerGroupMembership.REVIEW_REJECTED,
            reviewed_at=timezone.now(),
        )
    )


def _maybe_auto_promote(
    membership: BusinessPartnerGroupMembership,
    *,
    is_merge: bool,
) -> None:
    """Promove sugestão para 'accepted' ao atingir o threshold (não-merge)."""
    if is_merge:
        return
    if membership.review_status != BusinessPartnerGroupMembership.REVIEW_SUGGESTED:
        return
    if membership.hit_count < AUTO_PROMOTE_THRESHOLD:
        return
    membership.review_status = BusinessPartnerGroupMembership.REVIEW_ACCEPTED
    membership.reviewed_at = timezone.now()
    # reviewed_by stays None — system promotion, not user action.
    membership.save()
    _reject_conflicting_suggestions(
        membership.business_partner, keep_group_id=membership.group_id,
    )


@db_transaction.atomic
def upsert_membership_suggestion(
    bp_a: BusinessPartner,
    bp_b: BusinessPartner,
    *,
    method: str,
    source_id=None,
    confidence: Decimal = Decimal("0.5"),
    auto_promote_threshold: int = AUTO_PROMOTE_THRESHOLD,
) -> Optional[BusinessPartnerGroupMembership]:
    """Registra sinal de que ``bp_a`` e ``bp_b`` são o mesmo ator econômico.

    Retorna o membership tocado (criado ou atualizado), ou ``None`` quando
    não há nada a fazer. A função absorve seus próprios erros de DB —
    chamadores em hooks devem ainda envolver em try/except por segurança,
    seguindo o padrão de ``bump_version``.
    """
    if bp_a is None or bp_b is None or bp_a.id == bp_b.id:
        return None
    if bp_a.company_id != bp_b.company_id:
        logger.warning(
            "bp_group_service: refusing to group BPs from different tenants "
            "(bp_a.company=%s, bp_b.company=%s)",
            bp_a.company_id, bp_b.company_id,
        )
        return None

    company = bp_a.company
    confidence = Decimal(confidence)

    mem_a = _accepted_membership(bp_a)
    mem_b = _accepted_membership(bp_b)

    # Caso 1: ambos já estão no mesmo Group aceito.
    if mem_a and mem_b and mem_a.group_id == mem_b.group_id:
        # Sinal redundante; registra evidence em qualquer das duas linhas
        # (a do não-primary, para preservar histórico) sem alterar status.
        target = mem_a if mem_a.role != BusinessPartnerGroupMembership.ROLE_PRIMARY else mem_b
        if _evidence_already_recorded(target, method=method, source_id=source_id):
            return target
        _append_evidence(
            target, method=method, source_id=source_id,
            confidence=confidence, kind=EVIDENCE_KIND_NORMAL,
        )
        target.save()
        return target

    # Caso 2: ambos em Groups DIFERENTES — sugestão de merge.
    if mem_a and mem_b and mem_a.group_id != mem_b.group_id:
        # Determinístico: registra no Group de id menor; o "outro" BP
        # representado é o primary do Group oposto.
        if mem_a.group_id <= mem_b.group_id:
            target_group = mem_a.group
            other_primary_bp = mem_b.group.primary_partner
        else:
            target_group = mem_b.group
            other_primary_bp = mem_a.group.primary_partner

        membership, created = BusinessPartnerGroupMembership.objects.get_or_create(
            group=target_group,
            business_partner=other_primary_bp,
            defaults={
                "company": company,
                "role": BusinessPartnerGroupMembership.ROLE_MEMBER,
                "review_status": BusinessPartnerGroupMembership.REVIEW_SUGGESTED,
                "confidence": confidence,
                "hit_count": 1,
                "evidence": [],
            },
        )
        if not _evidence_already_recorded(membership, method=method, source_id=source_id):
            _append_evidence(
                membership, method=method, source_id=source_id,
                confidence=confidence, kind=EVIDENCE_KIND_MERGE,
            )
            if not created:
                membership.hit_count += 1
            membership.save()
        # NUNCA auto-promove merges — exige confirmação humana.
        return membership

    # Caso 3: nenhum em Group — cria Group novo.
    if not mem_a and not mem_b:
        primary_bp = _pick_primary(bp_a, bp_b)
        member_bp = bp_b if primary_bp.id == bp_a.id else bp_a

        group = BusinessPartnerGroup.objects.create(
            company=company,
            name=primary_bp.name,
            primary_partner=primary_bp,
        )
        BusinessPartnerGroupMembership.objects.create(
            company=company,
            group=group,
            business_partner=primary_bp,
            role=BusinessPartnerGroupMembership.ROLE_PRIMARY,
            review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
            confidence=Decimal("1.0"),
            hit_count=0,
            evidence=[],
            reviewed_at=timezone.now(),
        )
        membership = BusinessPartnerGroupMembership.objects.create(
            company=company,
            group=group,
            business_partner=member_bp,
            role=BusinessPartnerGroupMembership.ROLE_MEMBER,
            review_status=BusinessPartnerGroupMembership.REVIEW_SUGGESTED,
            confidence=confidence,
            hit_count=1,
            evidence=[],
        )
        _append_evidence(
            membership, method=method, source_id=source_id,
            confidence=confidence, kind=EVIDENCE_KIND_NORMAL,
        )
        membership.save()
        _maybe_auto_promote(membership, is_merge=False)
        return membership

    # Caso 4: exatamente um dos BPs já está num Group — sugere o outro nesse Group.
    existing = mem_a or mem_b
    target_group = existing.group
    member_bp = bp_b if existing.business_partner_id == bp_a.id else bp_a

    membership, created = BusinessPartnerGroupMembership.objects.get_or_create(
        group=target_group,
        business_partner=member_bp,
        defaults={
            "company": company,
            "role": BusinessPartnerGroupMembership.ROLE_MEMBER,
            "review_status": BusinessPartnerGroupMembership.REVIEW_SUGGESTED,
            "confidence": confidence,
            "hit_count": 1,
            "evidence": [],
        },
    )
    if _evidence_already_recorded(membership, method=method, source_id=source_id):
        return membership

    _append_evidence(
        membership, method=method, source_id=source_id,
        confidence=confidence, kind=EVIDENCE_KIND_NORMAL,
    )
    if not created:
        # Re-suggested or even rejected-then-re-suggested: count up and revive.
        if membership.review_status == BusinessPartnerGroupMembership.REVIEW_REJECTED:
            membership.review_status = BusinessPartnerGroupMembership.REVIEW_SUGGESTED
            membership.reviewed_at = None
            membership.reviewed_by = None
        membership.hit_count += 1
    membership.save()
    _maybe_auto_promote(membership, is_merge=False)
    return membership


def suggest_groups_from_reconciliation(
    company,
    bank_txs,
    journal_entries,
    *,
    reconciliation_id=None,
    confidence: Decimal = Decimal("0.85"),
) -> int:
    """Inspect a finalized reconciliation match and suggest groupings.

    Walks the unique CNPJ on each side (bank lines vs JE→Tx). For every
    ordered pair where both resolve to BPs and the BPs differ, calls
    ``upsert_membership_suggestion`` with ``method='bank_reconciliation'``.
    Returns the number of upserts attempted (mostly for observability).

    Defensive: any per-pair exception is swallowed and logged so a Group
    bug never blocks the reconciliation finalize.
    """
    if not bank_txs or not journal_entries:
        return 0

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

    if not bank_cnpjs or not je_cnpjs:
        return 0

    upserts = 0
    seen_pairs: set = set()
    for bank_cnpj in bank_cnpjs:
        bp_bank = resolve_bp_by_cnpj(company, bank_cnpj)
        if bp_bank is None:
            continue
        for je_cnpj in je_cnpjs:
            bp_book = resolve_bp_by_cnpj(company, je_cnpj)
            if bp_book is None or bp_book.id == bp_bank.id:
                continue
            pair = (min(bp_bank.id, bp_book.id), max(bp_bank.id, bp_book.id))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            try:
                upsert_membership_suggestion(
                    bp_bank, bp_book,
                    method="bank_reconciliation",
                    source_id=reconciliation_id,
                    confidence=confidence,
                )
                upserts += 1
            except Exception:
                logger.exception(
                    "bp_group_service: suggest from reconciliation failed "
                    "(rec=%s, bp_bank=%s, bp_book=%s)",
                    reconciliation_id, bp_bank.id, bp_book.id,
                )
    return upserts


@db_transaction.atomic
def ensure_root_group(bp: BusinessPartner) -> Optional[BusinessPartnerGroup]:
    """Ensure a Group exists for ``bp.cnpj_root`` and contains ``bp``.

    The "matriz/filial" relationship — multiple BPs sharing the first 8
    digits of their CNPJ — is structural (legally same PJ, different
    establishment). We materialize that as a real ``BusinessPartnerGroup``
    so all consolidation flows (reports, UI, alias scoring) go through a
    single primitive instead of branching on ``cnpj_root``.

    Behavior:
    - No-op when ``bp.cnpj_root`` is empty (CPF, foreign id, etc.).
    - No-op when ``bp`` is already in an accepted Group (any Group, not
      just root-derived). User-curated cross-root groupings take
      precedence; we don't override them.
    - When a root sibling is already in an accepted Group → add ``bp``
      as accepted member of that same Group.
    - When no sibling is in any Group yet → only create one if there's
      at least one other BP sharing the root (otherwise solo BPs don't
      need a group).

    Idempotent: safe to call repeatedly. Called from ``BusinessPartner.save``
    on every persist plus from the ``backfill_bp_groups`` mgmt command.
    """
    if not bp or not bp.cnpj_root or not bp.id:
        return None

    # Already in a group of any kind → leave it alone.
    if _accepted_membership(bp) is not None:
        return _accepted_membership(bp).group

    # Find an existing Group via any sibling that's already in one.
    sibling_membership = (
        BusinessPartnerGroupMembership.objects
        .filter(
            company=bp.company,
            review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
            business_partner__cnpj_root=bp.cnpj_root,
        )
        .exclude(business_partner_id=bp.id)
        .select_related('group')
        .first()
    )

    auto_evidence = [{
        'method': BusinessPartnerGroupMembership.METHOD_AUTO_ROOT,
        'source_id': None,
        'kind': 'auto_root',
    }]

    if sibling_membership is not None:
        BusinessPartnerGroupMembership.objects.get_or_create(
            group=sibling_membership.group,
            business_partner=bp,
            defaults={
                'company': bp.company,
                'role': BusinessPartnerGroupMembership.ROLE_MEMBER,
                'review_status': BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
                'confidence': Decimal('1.0'),
                'hit_count': 0,
                'evidence': list(auto_evidence),
                'reviewed_at': timezone.now(),
            },
        )
        return sibling_membership.group

    # No sibling has a group yet — only create one if there IS a sibling.
    siblings = list(
        BusinessPartner.objects
        .filter(company=bp.company, cnpj_root=bp.cnpj_root)
        .exclude(pk=bp.pk)
        .order_by('id')
    )
    if not siblings:
        return None

    all_bps = sorted([bp, *siblings], key=lambda b: b.id)
    primary = all_bps[0]
    others = all_bps[1:]

    group = BusinessPartnerGroup.objects.create(
        company=bp.company,
        name=primary.name,
        primary_partner=primary,
    )
    BusinessPartnerGroupMembership.objects.create(
        company=bp.company,
        group=group,
        business_partner=primary,
        role=BusinessPartnerGroupMembership.ROLE_PRIMARY,
        review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
        confidence=Decimal('1.0'),
        hit_count=0,
        evidence=list(auto_evidence),
        reviewed_at=timezone.now(),
    )
    for other in others:
        BusinessPartnerGroupMembership.objects.get_or_create(
            group=group,
            business_partner=other,
            defaults={
                'company': bp.company,
                'role': BusinessPartnerGroupMembership.ROLE_MEMBER,
                'review_status': BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
                'confidence': Decimal('1.0'),
                'hit_count': 0,
                'evidence': list(auto_evidence),
                'reviewed_at': timezone.now(),
            },
        )
    return group


def resolve_bp_by_cnpj(company, cnpj_or_cpf: str) -> Optional[BusinessPartner]:
    """Resolve string CNPJ/CPF para BP do mesmo tenant.

    Tenta match exato em ``identifier`` primeiro; se for CNPJ (14 dígitos)
    e não houver match exato, tenta resolver pela raiz — devolve o BP mais
    antigo com a mesma raiz como aproximação. Retorna ``None`` quando nada
    bate (caller pode então tratar como alias-only, fora do escopo deste
    módulo).
    """
    if not cnpj_or_cpf:
        return None
    digits = "".join(ch for ch in str(cnpj_or_cpf) if ch.isdigit())
    if not digits:
        return None
    bp = (
        BusinessPartner.objects
        .filter(company=company, identifier=digits)
        .order_by("id")
        .first()
    )
    if bp is not None:
        return bp
    if len(digits) == 14:
        return (
            BusinessPartner.objects
            .filter(company=company, cnpj_root=digits[:8])
            .order_by("id")
            .first()
        )
    return None
