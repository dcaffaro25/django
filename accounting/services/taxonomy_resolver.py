"""MPTT-walked taxonomy resolution for ``Account``.

The Account model carries two nullable taxonomy fields:

* ``report_category`` -- one of the 14 closed enum values (CPC 26 line
  items). Single-valued; the inheritance rule is **nearest-ancestor
  wins**: walk up the parent chain until a tagged ancestor is found.

* ``tags`` -- ArrayField of zero-or-more closed enum values
  (cross-cutting markers like ``cash``, ``debt``, ``contra_account``,
  ``ebitda_addback``, ...). Multi-valued; the inheritance rule is
  **union**: every ancestor contributes; child can ADD but not REMOVE.

Why asymmetric? Real-world cases:

  * A "(-) Depreciação Acumulada" leaf belongs in the same *category*
    as its parent ``Imobilizado`` (both ``ativo_nao_circulante``) but
    additionally needs the ``contra_account`` *tag*. Inheritance for
    category gives the right thing for free; inheritance for tags
    composes well with operator-set leaf tags.
  * Some level-1 nodes have mixed-category children (e.g. Evolat's
    ``Receita Operacional Líquida`` -> both ``receita_bruta`` and
    ``deducao_receita`` children). The operator tags at level 2 in
    those subtrees; nearest-ancestor inheritance handles the rest.
  * Tag union makes ``[fixed_asset, contra_account]`` come out
    naturally for a depreciation leaf when ``Imobilizado`` is tagged
    ``fixed_asset`` and the leaf is tagged ``contra_account`` -- both
    are operationally true and both filter through resolvers correctly.

The walk is in-Python, not SQL. For a typical tenant chart (300-500
accounts, MPTT depth ~5) this is O(N*depth) on the order of 1500
dict lookups per pass -- negligible. If we ever scale into 10k+
account charts the natural promotion is a recursive CTE; defer until
needed.

"""
from __future__ import annotations

from typing import Iterable, List, Optional, Set


def effective_category(account) -> Optional[str]:
    """Return the ``report_category`` that applies to this account
    after MPTT inheritance. Walks up parent chain until a node has a
    non-null ``report_category``; returns that. Self overrides any
    ancestor (explicit > implicit). Returns ``None`` if no ancestor
    is tagged -- the account is uncategorized.
    """
    node = account
    while node is not None:
        cat = getattr(node, "report_category", None)
        if cat:
            return cat
        node = getattr(node, "parent", None)
    return None


def effective_tags(account) -> List[str]:
    """Return the union of ``tags`` from this account and every
    ancestor. Sorted for deterministic ordering. Empty list when no
    ancestor (or self) carries any tag.
    """
    seen: Set[str] = set()
    node = account
    while node is not None:
        own = getattr(node, "tags", None) or []
        seen.update(own)
        node = getattr(node, "parent", None)
    return sorted(seen)


def has_tags(account, required: Iterable[str]) -> bool:
    """Convenience: ``True`` if every tag in ``required`` is in the
    account's effective tag set."""
    eff = set(effective_tags(account))
    return set(required).issubset(eff)


def has_any_tag(account, candidates: Iterable[str]) -> bool:
    """Convenience: ``True`` if at least one tag in ``candidates`` is
    in the account's effective tag set."""
    eff = set(effective_tags(account))
    return bool(set(candidates) & eff)


def categorize_qs(queryset, *, category: str):
    """Filter a queryset of ``Account`` rows down to those whose
    *effective* category equals ``category``. Materialises the queryset
    in Python because the inheritance walk isn't expressible in a
    single SQL filter without a recursive CTE.

    For tenant scopes (300-500 accounts) the cost is two list
    comprehensions; the queryset itself stays SQL-resolved up to the
    materialisation point.
    """
    accounts = list(queryset.select_related("parent"))
    matching_ids = [a.id for a in accounts if effective_category(a) == category]
    return queryset.filter(id__in=matching_ids)


def filter_qs_by_tags(queryset, *, all_of=None, any_of=None, none_of=None):
    """Filter a queryset of ``Account`` rows by effective-tag predicates.

    Three independent filters, all optional:
      * ``all_of`` -- account's effective tags must include EVERY tag
        in this iterable.
      * ``any_of`` -- account's effective tags must include AT LEAST
        ONE tag in this iterable.
      * ``none_of`` -- account's effective tags must include NONE of
        the tags in this iterable.
    """
    accounts = list(queryset.select_related("parent"))
    matching_ids = []
    all_set = set(all_of or [])
    any_set = set(any_of or [])
    none_set = set(none_of or [])
    for a in accounts:
        eff = set(effective_tags(a))
        if all_set and not all_set.issubset(eff):
            continue
        if any_set and not (any_set & eff):
            continue
        if none_set and (none_set & eff):
            continue
        matching_ids.append(a.id)
    return queryset.filter(id__in=matching_ids)
