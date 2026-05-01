# -*- coding: utf-8 -*-
"""
ProductServiceGroup — populador de sugestões a partir de heurísticas
de descoberta de SKUs equivalentes.

Diferente de ``bp_group_service`` (que aprende a partir de ações do
usuário em reconciliações / NF↔Tx), o lado produto raramente recebe
sinal episódico: o operador não "aceita" um produto contra outro como
faz com um match NF↔Tx. As sugestões precisam, portanto, vir de uma
varredura periódica do catálogo + de hooks no import.

Fontes de sinal implementadas:

1. ``suggest_groups_by_exact_name(company)`` — bucketiza ``ProductService``
   por nome normalizado (lower, sem acentos, espaços colapsados); cada
   cluster com ≥2 linhas vira um Group com role=primary no membro mais
   antigo e ``auto_name`` no(s) outro(s). Auto-promove na hora porque
   match de nome inteiro é evidência forte.
2. ``suggest_groups_by_head_token(company, head_size=3)`` — bucketiza
   pela cabeça (3 primeiros tokens, normalizados); clusters maiores que
   1 viram sugestões ``auto_head`` com hit_count=1 e *não* auto-promovem
   (fuzzier; precisa revisão humana).
3. Hooks futuros (não implementados aqui): ao linkar uma NF item a um
   ProductService, registrar uma sugestão entre ele e qualquer outro
   ProductService já visto com a mesma ``descricao`` na NF.

Promoção automática: ``auto_name`` (match exato) promove ao 1º hit;
``auto_head`` (match fuzzy) promove ao 3º hit. Conflitos (o mesmo
produto sugerido em múltiplos grupos) ficam suspensos -- o operador
arbitra.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction as db_transaction
from django.utils import timezone

from billing.models import (
    ProductService,
    ProductServiceAlias,
    ProductServiceGroup,
    ProductServiceGroupMembership,
)

logger = logging.getLogger(__name__)


AUTO_NAME_THRESHOLD = 1   # exact normalized name → auto-accept first hit
AUTO_HEAD_THRESHOLD = 3   # head-token prefix → 3 hits to auto-accept


# Tokens that don't contribute to product identity. Captures common
# non-discriminating noise — accounting captions, generic categories,
# packaging adjectives — so a single shared token like "produto" doesn't
# anchor a head-cluster.
_PRODUCT_TOKEN_STOPLIST = frozenset({
    "ind", "com", "produto", "produtos", "servico", "servicos",
    "material", "tipo", "novo", "nova", "novos", "novas",
    "kit", "pack", "caixa", "unidade",
    "und", "un", "pc", "pcs", "kg", "lt", "ml", "cm", "mm",
})


def _normalize_name(value) -> str:
    """Lowercase, strip diacritics, collapse whitespace, cap at 80 chars.

    Same shape as ``bp_alias_service._normalize_name``; kept independent
    so the two services don't accidentally couple via a shared mutable
    constant. Returns ``""`` for falsy input.
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


def _tokens(name: str) -> List[str]:
    """Split a normalized name into discriminating tokens. Drops pure
    numbers, single chars, and stoplisted noise."""
    if not name:
        return []
    out: List[str] = []
    for raw in re.split(r"[\s\-/.,;:|]+", name):
        if not raw or len(raw) < 2:
            continue
        if raw.isdigit():
            continue
        if raw in _PRODUCT_TOKEN_STOPLIST:
            continue
        out.append(raw)
    return out


def _head_key(name: str, head_size: int = 3) -> str:
    """Key used by ``auto_head``: the first ``head_size`` discriminating
    tokens joined by spaces. Returns ``""`` when the name has fewer
    than ``head_size`` discriminating tokens (we won't head-cluster
    those — too aggressive)."""
    toks = _tokens(name)
    if len(toks) < head_size:
        return ""
    return " ".join(toks[:head_size])


def _accepted_membership(
    ps: ProductService,
) -> Optional[ProductServiceGroupMembership]:
    return (
        ProductServiceGroupMembership.objects
        .filter(
            product_service=ps,
            review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
        )
        .select_related("group")
        .first()
    )


def _evidence_already_recorded(
    membership: ProductServiceGroupMembership,
    *,
    method: str,
    source_id,
) -> bool:
    if not membership.evidence:
        return False
    key = (method, source_id)
    for entry in membership.evidence:
        if (entry.get("method"), entry.get("source_id")) == key:
            return True
    return False


def _append_evidence(
    membership: ProductServiceGroupMembership,
    *,
    method: str,
    source_id,
    confidence: Decimal,
) -> None:
    membership.evidence.append({
        "method": method,
        "source_id": source_id,
        "at": timezone.now().isoformat(),
        "confidence": str(confidence),
    })
    if confidence > membership.confidence:
        membership.confidence = confidence


def _reject_conflicting_suggestions(
    ps: ProductService, *, keep_group_id: int,
) -> None:
    """When ``ps`` is accepted into Group X, suggestions for the same
    product in *other* groups stop making sense (one accepted group
    per product invariant)."""
    (
        ProductServiceGroupMembership.objects
        .filter(
            product_service=ps,
            review_status=ProductServiceGroupMembership.REVIEW_SUGGESTED,
        )
        .exclude(group_id=keep_group_id)
        .update(
            review_status=ProductServiceGroupMembership.REVIEW_REJECTED,
            reviewed_at=timezone.now(),
        )
    )


def _maybe_auto_promote(
    membership: ProductServiceGroupMembership,
    *,
    method: str,
) -> None:
    """Promote a ``suggested`` row to ``accepted`` when its method's
    threshold is met. Different thresholds per method:
        - auto_name: 1 (exact name match is strong)
        - auto_head: 3 (fuzzier)
        - manual / nf_item_link: never auto-promote (caller decides)
    """
    if membership.review_status != ProductServiceGroupMembership.REVIEW_SUGGESTED:
        return
    if method == ProductServiceGroupMembership.METHOD_AUTO_NAME:
        threshold = AUTO_NAME_THRESHOLD
    elif method == ProductServiceGroupMembership.METHOD_AUTO_HEAD:
        threshold = AUTO_HEAD_THRESHOLD
    else:
        return
    if membership.hit_count < threshold:
        return
    membership.review_status = ProductServiceGroupMembership.REVIEW_ACCEPTED
    membership.reviewed_at = timezone.now()
    membership.save()
    _reject_conflicting_suggestions(
        membership.product_service, keep_group_id=membership.group_id,
    )


def _ensure_group(
    company,
    primary: ProductService,
    members: List[ProductService],
    *,
    method: str,
    confidence: Decimal,
) -> ProductServiceGroup:
    """Create-or-fetch a Group rooted at ``primary``, then upsert one
    membership per ``member``. Evidence appended idempotently."""
    group, _created = ProductServiceGroup.objects.get_or_create(
        company=company,
        primary_product=primary,
        defaults={"name": primary.name},
    )
    # Primary membership (always accepted; structural).
    ProductServiceGroupMembership.objects.get_or_create(
        group=group,
        product_service=primary,
        defaults={
            "company": company,
            "role": ProductServiceGroupMembership.ROLE_PRIMARY,
            "review_status": ProductServiceGroupMembership.REVIEW_ACCEPTED,
            "confidence": Decimal("1.0"),
            "hit_count": 0,
            "evidence": [],
            "reviewed_at": timezone.now(),
        },
    )
    for ps in members:
        membership, created = ProductServiceGroupMembership.objects.get_or_create(
            group=group,
            product_service=ps,
            defaults={
                "company": company,
                "role": ProductServiceGroupMembership.ROLE_MEMBER,
                "review_status": ProductServiceGroupMembership.REVIEW_SUGGESTED,
                "confidence": confidence,
                "hit_count": 1,
                "evidence": [],
            },
        )
        if _evidence_already_recorded(membership, method=method, source_id=primary.id):
            continue
        _append_evidence(
            membership,
            method=method,
            source_id=primary.id,
            confidence=confidence,
        )
        if not created:
            if membership.review_status == ProductServiceGroupMembership.REVIEW_REJECTED:
                membership.review_status = ProductServiceGroupMembership.REVIEW_SUGGESTED
                membership.reviewed_at = None
                membership.reviewed_by = None
            membership.hit_count += 1
        membership.save()
        _maybe_auto_promote(membership, method=method)
    return group


@db_transaction.atomic
def suggest_groups_by_exact_name(company) -> dict:
    """Cluster ProductService rows by normalized full name; each
    cluster of size ≥2 gets a Group with the oldest member as primary.

    Auto-promotes ``auto_name`` memberships on the first hit -- matching
    a full normalized name is strong evidence (Evolat survey: clusters
    are real dupes, not coincidences). Returns counters for caller
    reporting (mgmt command, etc.)."""
    rows = list(
        ProductService.objects
        .filter(company=company, is_active=True)
        .order_by("id")
        .only("id", "name")
    )
    buckets: Dict[str, List[ProductService]] = defaultdict(list)
    for ps in rows:
        key = _normalize_name(ps.name)
        if not key:
            continue
        buckets[key].append(ps)

    counters = {"clusters": 0, "memberships_upserted": 0, "products_in_clusters": 0}
    for key, cluster in buckets.items():
        if len(cluster) < 2:
            continue
        # Oldest member is the primary. Stable, deterministic.
        cluster.sort(key=lambda p: p.id)
        primary, *members = cluster
        try:
            _ensure_group(
                company,
                primary,
                members,
                method=ProductServiceGroupMembership.METHOD_AUTO_NAME,
                confidence=Decimal("0.95"),
            )
            counters["clusters"] += 1
            counters["memberships_upserted"] += len(members)
            counters["products_in_clusters"] += len(cluster)
        except Exception:
            logger.exception(
                "ps_group_service: exact-name cluster upsert failed "
                "(company=%s, key=%r, primary=%s)",
                company.id, key, primary.id,
            )
    return counters


@db_transaction.atomic
def suggest_groups_by_head_token(
    company, *, head_size: int = 3,
) -> dict:
    """Cluster ProductService rows by the first ``head_size`` tokens
    of their normalized name. Each cluster of size ≥2 gets ``auto_head``
    suggestions (NOT auto-promoted on first hit -- requires
    AUTO_HEAD_THRESHOLD=3 independent observations).

    Catches cases like "1004 - naveia barista 1l x 12" vs
    "naveia barista 1l" — which exact-name doesn't catch but share
    the same first three discriminating tokens."""
    rows = list(
        ProductService.objects
        .filter(company=company, is_active=True)
        .order_by("id")
        .only("id", "name")
    )
    buckets: Dict[str, List[ProductService]] = defaultdict(list)
    for ps in rows:
        key = _head_key(_normalize_name(ps.name), head_size=head_size)
        if not key:
            continue
        buckets[key].append(ps)

    counters = {"clusters": 0, "memberships_upserted": 0, "products_in_clusters": 0}
    for key, cluster in buckets.items():
        if len(cluster) < 2:
            continue
        cluster.sort(key=lambda p: p.id)
        primary, *members = cluster
        try:
            _ensure_group(
                company,
                primary,
                members,
                method=ProductServiceGroupMembership.METHOD_AUTO_HEAD,
                confidence=Decimal("0.7"),
            )
            counters["clusters"] += 1
            counters["memberships_upserted"] += len(members)
            counters["products_in_clusters"] += len(cluster)
        except Exception:
            logger.exception(
                "ps_group_service: head-token cluster upsert failed "
                "(company=%s, key=%r, primary=%s)",
                company.id, key, primary.id,
            )
    return counters


def find_shared_group(
    ps_a: Optional[ProductService],
    ps_b: Optional[ProductService],
) -> Optional[ProductServiceGroup]:
    """Return the accepted Group that contains both products, or None."""
    if ps_a is None or ps_b is None or ps_a.id == ps_b.id:
        return None
    mem_a = (
        ProductServiceGroupMembership.objects
        .filter(
            product_service_id=ps_a.id,
            review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
        )
        .select_related("group")
        .first()
    )
    if mem_a is None:
        return None
    mem_b = (
        ProductServiceGroupMembership.objects
        .filter(
            product_service_id=ps_b.id,
            group_id=mem_a.group_id,
            review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
        )
        .first()
    )
    return mem_a.group if mem_b is not None else None


def resolve_ps_by_code(company, code: str) -> Optional[ProductService]:
    """Resolve an external code to a ProductService.

    1. Exact match on ``ProductService.code`` (the primary key in the
       catalog for most ERPs).
    2. Accepted ``ProductServiceAlias(kind=code)`` fallback — lets us
       resolve a code that was previously seen under a different
       ProductService row to its canonical / consolidated entry.
    """
    if not code or company is None:
        return None
    code = code.strip()
    if not code:
        return None
    ps = (
        ProductService.objects
        .filter(company=company, code=code)
        .order_by("id")
        .first()
    )
    if ps is not None:
        return ps
    alias = (
        ProductServiceAlias.objects
        .filter(
            company=company,
            kind=ProductServiceAlias.KIND_CODE,
            alias_identifier=code,
            review_status=ProductServiceAlias.REVIEW_ACCEPTED,
        )
        .select_related("product_service")
        .first()
    )
    return alias.product_service if alias is not None else None


def resolve_ps_by_name(company, name: str) -> Optional[ProductService]:
    """Resolve a product name (e.g. NF item ``descricao``) to a
    ProductService via accepted name aliases. Useful when the import
    sees an unfamiliar code but a name we've seen before."""
    token = _normalize_name(name)
    if not token or company is None:
        return None
    alias = (
        ProductServiceAlias.objects
        .filter(
            company=company,
            kind=ProductServiceAlias.KIND_NAME,
            alias_identifier=token,
            review_status=ProductServiceAlias.REVIEW_ACCEPTED,
        )
        .select_related("product_service")
        .first()
    )
    return alias.product_service if alias is not None else None
