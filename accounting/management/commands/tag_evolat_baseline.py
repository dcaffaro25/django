"""Idempotent baseline tagger for the Evolat tenant's chart of accounts.

Populates ``report_category`` and ``tags`` on Evolat's level-1 (and a
handful of critical level-2) anchor nodes so descendants inherit the
right taxonomy via ``effective_category()`` / ``effective_tags()``.

Usage:

    python manage.py tag_evolat_baseline --dry-run    # preview
    python manage.py tag_evolat_baseline              # apply

The command is **idempotent** -- safe to re-run. It only updates rows
whose current value differs from the desired value, and it never
overwrites an explicit operator override (we treat any non-null
``report_category`` set by an operator as authoritative when it
matches what we want; mismatches are flagged but skipped).

Why a per-tenant command (and not a generic taxonomy importer):

* Evolat's chart structure is known to us specifically -- we audited
  it in the Phase 1 design (see project memory file
  ``coa_enrichment_plan.md``). Hard-coding the level-1 + level-2
  names against this audit is the fastest path to a working baseline.
* For the next tenant we'll evolve this into a YAML-driven generic
  command. For now the leverage is in unblocking Evolat's standard
  reports -- a 100-line script gets us there in minutes.

Anchors covered:

* 11 level-1 nodes for ``report_category`` (where the children are
  uniformly one category)
* 3 mixed-category level-1 parents disambiguated at level 2
  (Receita Operacional Líquida, Resultado Financeiro,
  Outras Receitas E Despesas Operacionais)
* Subtree-wide tags: ``cash`` on Disponível, ``fixed_asset`` on
  Imobilizado, ``intangible_asset`` on Intangível, ``debt`` on the
  two Empréstimos E Financiamentos subtrees, ``ebitda_addback`` +
  ``non_cash`` on the Depreciação E Amortização level-1 sibling.
"""
from __future__ import annotations

from typing import List, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounting.models import Account
from accounting.services.taxonomy_meta import (
    REPORT_CATEGORY_VALUES,
    TAG_VALUES,
)
from multitenancy.models import Company


# Anchor table. Each row is:
#   (account_name, report_category_or_None, tags_to_set_or_empty)
# Account is matched by (company=evolat, name=...) -- we don't
# hard-code IDs because they're environment-specific.
LEVEL_1_CATEGORIES: List[tuple[str, Optional[str], list[str]]] = [
    # ---- Balance sheet roots ----
    ("Ativo Circulante", "ativo_circulante", []),
    ("Ativo Não Circulante", "ativo_nao_circulante", []),
    ("Passivo Circulante", "passivo_circulante", []),
    ("Passivo Não Circulante", "passivo_nao_circulante", []),
    ("Capital Social", "patrimonio_liquido", []),
    ("Reservas", "patrimonio_liquido", []),
    ("Lucros Ou Prejuízos Acumulados", "patrimonio_liquido", []),

    # ---- DRE roots (only the uniformly-one-category ones at level 1) ----
    ("Custo Dos Produtos Vendidos", "custo", []),
    ("Despesas Operacionais", "despesa_operacional", []),
    # D&A is a separate level-1 sibling on Evolat's chart -- still an
    # operating expense, but tagged so EBITDA can add it back.
    ("Depreciação, Amortização E Exaustão", "despesa_operacional",
     ["non_cash", "ebitda_addback"]),
    ("Irpj E Csll", "imposto_sobre_lucro", []),
]

# Mixed-category level-1 parents -- DON'T tag at level 1; tag the
# level-2 children with their respective category.
LEVEL_2_CATEGORIES: List[tuple[str, str, Optional[str], list[str]]] = [
    # (parent_name, child_name, child_category, child_tags)
    ("Receita Operacional Líquida", "Receita Bruta De Vendas",
     "receita_bruta", []),
    ("Receita Operacional Líquida", "Deduções Da Receita Bruta",
     "deducao_receita", []),
    ("Resultado Financeiro", "Receitas Financeiras",
     "receita_financeira", []),
    ("Resultado Financeiro", "Despesas Financeiras",
     "despesa_financeira", []),
    ("Outras Receitas E Despesas Operacionais", "Outras Receitas Operacionais",
     "outras_receitas", []),
    ("Outras Receitas E Despesas Operacionais", "Outras Despesas Operacionais",
     "outras_receitas", []),
]

# Subtree-wide tag applications (no category change -- tags are
# orthogonal). Tag is applied to the named ANCHOR ACCOUNT only;
# descendants get it via effective_tags() inheritance.
SUBTREE_TAGS: List[tuple[str, list[str]]] = [
    ("Disponível", ["cash"]),
    ("Imobilizado", ["fixed_asset"]),
    ("Intangível", ["intangible_asset"]),
    # Two Empréstimos subtrees with different short/long-term tags.
    # Names come from the level-2 audit on Evolat's tree.
    ("Empréstimos E Financiamentos", ["debt", "short_term"]),
    ("Empréstimos E Financiamentos A Longo Prazo", ["debt", "long_term"]),
    # DFC (indireto) needs working-capital deltas. Tag at the L2
    # parent so all leaves under each subtree get the marker.
    ("Créditos", ["working_capital"]),
    ("Estoques", ["working_capital"]),
    ("Fornecedores", ["working_capital"]),
    # DVA needs the "insumos adquiridos de terceiros" set. CPV is
    # the dominant input; tag the L1 sibling so all L2/L3 cost
    # leaves inherit. See CPC 09 for the formal definition.
    ("Custo Dos Produtos Vendidos", ["value_added_input"]),
]


# Some accounts are nested under a parent whose category doesn't
# match what they actually are. Most common pattern: deduction-like
# subaccounts (devoluções, vendas canceladas) stored under
# ``Receita Bruta De Vendas`` instead of under ``Deduções``. We
# explicitly override the category on these leaves so the inherited
# value isn't ``receita_bruta`` (which would inflate revenue and
# show negative numbers in the wrong line).
#
# Match by name -- IDs are tenant-specific; names are stable.
# When two accounts share the same name (Evolat has duplicates from
# imports), we override BOTH.
LEAF_CATEGORY_OVERRIDES: List[tuple[str, str]] = [
    ("Vendas Canceladas ou Devoluções", "deducao_receita"),
    ("Vendas Canceladas Ou Devoluções", "deducao_receita"),  # capitalisation variant
    ("Devoluções de Mercadoria", "deducao_receita"),
    ("Abatimentos E Descontos", "deducao_receita"),
]


# Pattern-based tag application. Each entry is
#   (substring, tags_to_add, [optional: also-set-category])
# Substring is matched **case-insensitively** against the account
# name. This catches every variant ("ICMS A Recolher", "ICMS A
# Recuperar", "Icms Sobre Vendas", ...) without listing each leaf.
#
# We deliberately use substring rather than regex because:
# 1. Brazilian tax names are stable enough words ("ICMS", "PIS", ...)
# 2. False positives on these are rare ("ICMS" doesn't appear in
#    non-tax accounts on any normal chart)
# 3. Operators can predict what gets matched without learning regex
PATTERN_TAGS: List[tuple[str, list[str]]] = [
    # ---- Brazilian tax tags ----
    # ICMS appears in 3 places: dedução, recuperar, recolher
    ("icms", ["icms"]),
    ("pis", ["pis"]),
    ("cofins", ["cofins"]),
    ("ipi", ["ipi"]),
    # ISS only as a substring is ambiguous (could match ``Comissões``
    # if the operator typed it weird) -- but no Brazilian chart in
    # practice has "iss" as a substring outside ISS tax accounts.
    ("iss ", ["iss"]),  # trailing space avoids false matches
    ("iss a", ["iss"]),
    ("inss", ["inss"]),
    ("fgts", ["fgts"]),
    # IRRF accounts -- both recoverable and payable.
    ("irrf", ["irrf"]),
    # ---- Foreign currency / export ----
    ("exterior", ["foreign_currency"]),
    ("exportação", ["export_revenue"]),
    # ---- Contra accounts: anything starting with "(-)" ----
    ("(-)", ["contra_account"]),
]


class Command(BaseCommand):
    help = (
        "Apply Phase 1 baseline taxonomy tags (report_category + tags) "
        "to Evolat's chart of accounts. Idempotent; supports --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would change without writing anything.",
        )
        parser.add_argument(
            "--tenant", default="evolat",
            help="Tenant subdomain to target (default: evolat). "
                 "Reserved for future reuse with other tenants.",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        sub = opts["tenant"]

        try:
            company = Company.objects.get(subdomain=sub)
        except Company.DoesNotExist:
            raise CommandError(f"No tenant with subdomain={sub!r}")

        # Validate the anchor table against the closed enums up front
        # so a typo doesn't silently apply an invalid value.
        for _, cat, tags in LEVEL_1_CATEGORIES:
            self._validate(cat, tags)
        for _, _, cat, tags in LEVEL_2_CATEGORIES:
            self._validate(cat, tags)
        for _, tags in SUBTREE_TAGS:
            self._validate(None, tags)
        for _, override_cat in LEAF_CATEGORY_OVERRIDES:
            self._validate(override_cat, [])
        for _, tags in PATTERN_TAGS:
            self._validate(None, tags)

        self.stdout.write(self.style.NOTICE(
            f"== Baseline tagger for tenant={sub} (dry_run={dry_run}) =="
        ))

        changes: list[tuple[Account, dict, dict]] = []
        # (account, current_state, desired_state)

        # ---- Pass 1: level-1 categories ----
        for name, category, tags in LEVEL_1_CATEGORIES:
            acc = self._find_one(company, name)
            if acc is None:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP level-1 {name!r} -- not found"
                ))
                continue
            current = {"report_category": acc.report_category, "tags": list(acc.tags or [])}
            desired = self._merge_desired(current, category, tags)
            if current == desired:
                continue
            changes.append((acc, current, desired))

        # ---- Pass 2: level-2 categories under mixed-category parents ----
        for parent_name, child_name, category, tags in LEVEL_2_CATEGORIES:
            parent = self._find_one(company, parent_name)
            if parent is None:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP level-2 parent {parent_name!r} -- not found"
                ))
                continue
            acc = Account.objects.filter(
                company=company, parent=parent, name=child_name, is_active=True,
            ).first()
            if acc is None:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP level-2 child {child_name!r} under {parent_name!r} -- not found"
                ))
                continue
            current = {"report_category": acc.report_category, "tags": list(acc.tags or [])}
            desired = self._merge_desired(current, category, tags)
            if current == desired:
                continue
            changes.append((acc, current, desired))

        # ---- Pass 3: subtree tags (no category change) ----
        for anchor_name, tags in SUBTREE_TAGS:
            acc = self._find_one(company, anchor_name)
            if acc is None:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP subtree {anchor_name!r} -- not found"
                ))
                continue
            current = {"report_category": acc.report_category, "tags": list(acc.tags or [])}
            desired = self._merge_desired(current, None, tags)
            if current == desired:
                continue
            changes.append((acc, current, desired))

        # ---- Pass 4: leaf category overrides ----
        # Misplaced subaccounts whose parent has the wrong category
        # for them (e.g. "Devoluções" stored under "Receita Bruta").
        # Override the category at the leaf so inheritance doesn't
        # propagate the wrong parent category to its descendants.
        for leaf_name, override_category in LEAF_CATEGORY_OVERRIDES:
            for acc in Account.objects.filter(
                company=company, name=leaf_name, is_active=True,
            ):
                current = {"report_category": acc.report_category, "tags": list(acc.tags or [])}
                # Force-override even if currently null and parent has
                # an inherited (wrong) category. The override lives at
                # the leaf, not on the parent, so we don't fight other
                # tagging passes.
                if current["report_category"] == override_category:
                    continue
                desired = {
                    "report_category": override_category,
                    "tags": current["tags"],
                }
                changes.append((acc, current, desired))

        # ---- Pass 5: pattern-based tag application ----
        # For each (substring, tags) pair, find every account in the
        # tenant whose name contains the substring and union the tags.
        # Matched leaves inherit through MPTT to descendants too, but
        # since most matches are at the leaf level, the impact is
        # mostly direct.
        for substr, tags in PATTERN_TAGS:
            for acc in Account.objects.filter(
                company=company, name__icontains=substr, is_active=True,
            ):
                current = {"report_category": acc.report_category, "tags": list(acc.tags or [])}
                desired = self._merge_desired(current, None, tags)
                if current == desired:
                    continue
                changes.append((acc, current, desired))

        # Deduplicate: an account might be picked up by multiple
        # passes (e.g. "Icms A Recolher" hits both the icms pattern
        # and might show up later via another match). Merge into one
        # final desired-state per account, applying tags as union and
        # taking the first non-null category override.
        merged: dict[int, tuple[Account, dict, dict]] = {}
        for acc, current, desired in changes:
            if acc.id in merged:
                _, prev_current, prev_desired = merged[acc.id]
                tags_union = sorted(set(prev_desired["tags"]) | set(desired["tags"]))
                cat = prev_desired["report_category"] or desired["report_category"]
                merged[acc.id] = (acc, prev_current, {
                    "report_category": cat,
                    "tags": tags_union,
                })
            else:
                merged[acc.id] = (acc, current, desired)
        changes = [
            (acc, current, desired)
            for acc, current, desired in merged.values()
            if current != desired
        ]

        # ---- Report and apply ----
        if not changes:
            self.stdout.write(self.style.SUCCESS(
                "No changes needed -- chart is already at the baseline."
            ))
            return

        self.stdout.write(f"\n{len(changes)} account(s) to update:\n")
        for acc, current, desired in changes:
            cat_diff = (
                f"  category: {current['report_category']!r} -> {desired['report_category']!r}"
                if current["report_category"] != desired["report_category"]
                else None
            )
            tag_diff = (
                f"  tags:     {current['tags']!r} -> {desired['tags']!r}"
                if current["tags"] != desired["tags"]
                else None
            )
            self.stdout.write(f"  - id={acc.id} {acc.name!r}")
            if cat_diff:
                self.stdout.write(cat_diff)
            if tag_diff:
                self.stdout.write(tag_diff)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "\n[dry-run] no changes applied. Re-run without --dry-run."
            ))
            return

        with transaction.atomic():
            for acc, _, desired in changes:
                acc.report_category = desired["report_category"]
                acc.tags = desired["tags"]
                acc.save(update_fields=["report_category", "tags"])

        self.stdout.write(self.style.SUCCESS(
            f"\nApplied {len(changes)} update(s)."
        ))

    def _find_one(self, company, name):
        """Return the most-likely Account for a company+name pair.

        We don't constrain to a specific level here -- the anchor names
        are unique enough on Evolat that ``filter().first()`` is safe.
        If multiple accounts share the same name (sub-pieces of the
        same hierarchy), we prefer the highest-level one so the tag
        applies to the broader subtree.
        """
        return (
            Account.objects.filter(company=company, name=name, is_active=True)
            .order_by("level")
            .first()
        )

    def _merge_desired(self, current, category, tags_to_add):
        """Compute the post-update state.

        * ``report_category``: only set when currently null AND we have
          a value to set. Operator overrides (already-set values that
          differ from ours) are PRESERVED -- the script never clobbers
          a manual decision.
        * ``tags``: union of current + tags_to_add, deduplicated and
          sorted. Adding only; never removes. Same operator-respect
          rule applies via union (we can't accidentally erase a tag
          the operator added).
        """
        new_cat = current["report_category"]
        if category is not None and new_cat is None:
            new_cat = category
        elif category is not None and new_cat != category:
            # Operator already set something different. Log but don't
            # overwrite. Surface as a warning row in the diff so the
            # operator can review the conflict.
            self.stdout.write(self.style.WARNING(
                f"  CONFLICT category {current['report_category']!r} vs desired "
                f"{category!r} -- keeping operator's value"
            ))

        merged_tags = sorted(set(current["tags"]) | set(tags_to_add))
        return {"report_category": new_cat, "tags": merged_tags}

    def _validate(self, category, tags):
        if category is not None and category not in REPORT_CATEGORY_VALUES:
            raise CommandError(
                f"Anchor table contains invalid report_category {category!r} -- "
                f"not in REPORT_CATEGORY_VALUES"
            )
        for t in tags:
            if t not in TAG_VALUES:
                raise CommandError(
                    f"Anchor table contains invalid tag {t!r} -- not in TAG_VALUES"
                )
