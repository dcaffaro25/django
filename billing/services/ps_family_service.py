# -*- coding: utf-8 -*-
"""
ProductServiceCategory bootstrap — induce a family taxonomy from
existing product names.

The tenant's ``ProductServiceCategory`` MPTT tree is typically empty
(Evolat: 26 of 986 products have a category, all 8 categories are
flat). The family signal lives in the product names themselves —
brand at the start, line / size / flavor as suffixes:

    "1003 - NAVEIA ORIGINAL 1L X 12"
    "PAPEL CARTAO NAO BRANQUEADO C/PE..."
    "CABO FLEXIVEL 4,0 MM2 PRETO MEGATRON"

This module bootstraps a starter tree by clustering products by their
**first content token** (skipping leading numeric codes / separators /
stoplisted noise). Each cluster of ≥``min_cluster`` products becomes
a root ``ProductServiceCategory``; products land on those roots.

Why first-content-token, not raw frequency:
    Raw token frequency picks up modifiers ("ind", "cartao", "branco")
    that aren't brands. The first content token (after stripping
    leading codes) is almost always the brand or family head — a
    stronger heuristic with much less noise.

Operator workflow:
    The tree is meant to be edited. Auto-created categories are a
    *starting point*; operators rename, merge, split, and add depth
    via the existing categories admin / UI. The bootstrap is
    idempotent — running it again won't move products that already
    have a category, and won't recreate already-existing root
    categories. Safe to re-run after operator edits.

Not in this module (deferred):
    * Multi-level recursion (Naveia → Deleitinho → Chocolate). The
      first level catches the biggest win; depth can be added later.
    * Tag extraction (size, vendor, channel) — orthogonal to the
      tree axis; planned as JSONField on ProductService.
    * Bundle composition — separate concept entirely.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Optional

from django.db import transaction as db_transaction

from billing.models import ProductService, ProductServiceCategory

logger = logging.getLogger(__name__)


# Tokens we never use as a category root. Keep small; expand as
# operators flag noise. Lowercase, no diacritics (post-normalization
# form).
_FAMILY_TOKEN_STOPLIST = frozenset({
    # Generic descriptors
    "ind", "com", "produto", "produtos", "servico", "servicos",
    "material", "tipo", "novo", "nova", "novos", "novas", "kit",
    "pack", "caixa", "unidade", "und", "un", "pc", "pcs",
    # Adjectives that aren't brand/family heads
    "branco", "preto", "azul", "verde", "vermelho", "amarelo",
    "novo", "novos", "usado", "padrao", "standard",
})

_NUM_OR_SEP_RE = re.compile(r"^[\d\s\-/.,;:|()#%&*]+$")


def _normalize_name(value) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    if not value:
        return ""
    s = str(value).strip().lower()
    s = "".join(
        ch for ch in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", s)


def _first_content_token(name: str) -> Optional[str]:
    """Extract the first 'name-like' token from a product name.

    Skips leading numeric codes, separator-only chunks, single-char
    fragments, and stoplisted descriptors. Returns ``None`` when the
    name has no content token (e.g. just numbers / punctuation).
    """
    norm = _normalize_name(name)
    if not norm:
        return None
    for raw in re.split(r"[\s\-/.,;:|]+", norm):
        if not raw or len(raw) < 3:
            continue
        if _NUM_OR_SEP_RE.match(raw):
            continue
        if raw.isdigit():
            continue
        if raw in _FAMILY_TOKEN_STOPLIST:
            continue
        return raw
    return None


def _title_case(token: str) -> str:
    """Display name for an auto-created category. ``naveia`` → ``Naveia``."""
    return token.capitalize()


@db_transaction.atomic
def bootstrap_family_tree(
    company,
    *,
    min_cluster: int = 5,
    overwrite_existing: bool = False,
    dry_run: bool = False,
) -> dict:
    """Induce a 1-level family tree from product names.

    Args:
        company: tenant.
        min_cluster: minimum products per cluster for a category to be
            created. Tokens with fewer products fall through and
            their products stay uncategorized — keeps the tree
            focused on signal-bearing groups.
        overwrite_existing: when False (default), products with a
            ``category`` already set are left alone. Set True to
            re-bootstrap from scratch (operator escape hatch).
        dry_run: wraps writes in a savepoint that rolls back at the
            end. Returns the same counters as a real run so the
            caller can preview impact.

    Returns counter dict:
        {
          'products_scanned',
          'tokens_above_threshold',
          'categories_created',
          'categories_reused',
          'products_assigned',
          'products_unchanged_existing_category',
          'products_uncategorized_below_threshold',
          'sample_clusters': [(token, count, sample_names), ...]
        }
    """
    qs = ProductService.objects.filter(company=company, is_active=True)
    products = list(qs.only("id", "name", "category_id"))

    counters = {
        "products_scanned": len(products),
        "tokens_above_threshold": 0,
        "categories_created": 0,
        "categories_reused": 0,
        "products_assigned": 0,
        "products_unchanged_existing_category": 0,
        "products_uncategorized_below_threshold": 0,
        "sample_clusters": [],
    }

    # 1. Bucket by first content token.
    buckets: Dict[str, List[ProductService]] = defaultdict(list)
    no_token = 0
    for ps in products:
        if ps.category_id is not None and not overwrite_existing:
            counters["products_unchanged_existing_category"] += 1
            continue
        token = _first_content_token(ps.name)
        if token is None:
            no_token += 1
            continue
        buckets[token].append(ps)

    # 2. For each token with ≥ min_cluster products, create / reuse
    #    a root category and assign products.
    eligible = [
        (tok, members)
        for tok, members in buckets.items()
        if len(members) >= min_cluster
    ]
    eligible.sort(key=lambda kv: -len(kv[1]))
    counters["tokens_above_threshold"] = len(eligible)

    sample_buf = []
    for token, members in eligible:
        display = _title_case(token)
        # Idempotent root lookup: by company + name, root level
        # (parent=None). MPTT keeps tree state consistent through
        # ``parent`` writes.
        cat = ProductServiceCategory.objects.filter(
            company=company, parent__isnull=True, name=display,
        ).first()
        if cat is None:
            cat = ProductServiceCategory.objects.create(
                company=company, name=display, parent=None,
            )
            counters["categories_created"] += 1
        else:
            counters["categories_reused"] += 1

        ids = [m.id for m in members]
        assignable_qs = ProductService.objects.filter(
            company=company, id__in=ids,
        )
        if not overwrite_existing:
            assignable_qs = assignable_qs.filter(category__isnull=True)
        assigned = assignable_qs.update(category=cat)
        counters["products_assigned"] += assigned

        if len(sample_buf) < 8:
            sample_names = [m.name for m in members[:3]]
            sample_buf.append((token, len(members), sample_names))

    # 3. Products in below-threshold buckets stay uncategorized so the
    #    tree only carries clusters with real signal.
    for tok, members in buckets.items():
        if len(members) < min_cluster:
            counters["products_uncategorized_below_threshold"] += len(members)

    counters["sample_clusters"] = sample_buf

    if dry_run:
        db_transaction.set_rollback(True)

    return counters
