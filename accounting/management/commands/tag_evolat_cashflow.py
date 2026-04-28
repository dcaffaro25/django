"""Idempotent cashflow_category tagger for Evolat.

Populates ``cashflow_category`` on Evolat's anchor accounts so the DFC
direct-method aggregation has a clean section + sub-line breakdown.
Inheritance follows the same MPTT walk as ``report_category`` -- tag
at the highest level where every descendant fits the same DFC line,
override at level 2/3 when the parent is mixed.

Usage:

    python manage.py tag_evolat_cashflow --dry-run     # preview
    python manage.py tag_evolat_cashflow               # apply

Idempotent: only writes rows whose current value differs from the
desired value. Safe to re-run after operator edits via the wiring
modal -- explicit operator overrides are preserved when they don't
match the desired anchor (we log the conflict but skip the write).

Tagging policy:

* **Cash accounts stay UNTAGGED.** "Disponível" and bank sub-accounts
  ARE the cash; assigning them a DFC line would double-count.
* **Anchor at the highest uniform level.** "Custo Dos Produtos
  Vendidos" tags as ``fco_pagamentos_fornecedores`` once at level 1;
  every descendant inherits.
* **Pattern overrides for mixed subtrees.** "Despesas Operacionais"
  has both supplier and employee payments under it; we set the
  subtree default to fornecedores and override empregados-related
  leaves by name match.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounting.models import Account
from accounting.services.taxonomy_meta import CASHFLOW_CATEGORY_VALUES
from multitenancy.models import Company


# ---------------------------------------------------------------------
# Anchor tables
# ---------------------------------------------------------------------

# Set on the named account; descendants inherit.
# Ordered most-general first so later (more specific) anchors can
# refine via the override pass.
SUBTREE_ANCHORS: List[Tuple[str, str]] = [
    # ---- Operating: customers / suppliers ----
    ("A Receber de Clientes", "fco_recebimentos_clientes"),
    ("Receita Bruta De Vendas", "fco_recebimentos_clientes"),
    # Receita "Deduções" are net-of-cash-receipts adjustments —
    # they reduce what the customer effectively pays. Keep with the
    # receivables bucket so the FCO line is one consolidated number.
    ("Deduções Da Receita Bruta", "fco_recebimentos_clientes"),

    # All product cost flows are supplier payments (Brazilian
    # practice: matérias-primas, frete, industrialização external).
    ("Custo Dos Produtos Vendidos", "fco_pagamentos_fornecedores"),
    ("Fornecedores", "fco_pagamentos_fornecedores"),
    ("Estoques", "fco_pagamentos_fornecedores"),
    ("Matérias-Primas - Produto", "fco_pagamentos_fornecedores"),
    ("Produtos Acabados - Custo", "fco_pagamentos_fornecedores"),

    # Default bucket for Despesas Operacionais — fornecedores is the
    # majority case (frete, aluguel, telefonia, marketing,
    # consultorias, terceiros). Empregados / impostos / juros are
    # overridden via name patterns below.
    ("Despesas Operacionais", "fco_pagamentos_fornecedores"),
    ("Servicos De Terceiros", "fco_pagamentos_fornecedores"),
    ("Serviços De Terceiros", "fco_pagamentos_fornecedores"),

    # ---- Operating: taxes ----
    ("Irpj E Csll", "fco_imposto_renda"),

    # ---- Operating: financial result ----
    # Juros pagos and rendimentos recebidos under the same FCO line
    # per CPC 03.31 (Brazilian common practice).
    ("Receitas Financeiras", "fco_juros"),
    ("Despesas Financeiras", "fco_juros"),

    # ---- Investing ----
    ("Imobilizado", "fci_imobilizado"),
    ("Intangível", "fci_intangivel"),
    # The user's specific concern: "Saldo do Principal Aplicado" is
    # a financial investment, not an operational current asset.
    ("Aplicações Financeiras De Liquidez Imediata",
     "fci_investimentos_financeiros"),

    # ---- Financing ----
    ("Empréstimos E Financiamentos", "fcf_emprestimos"),
    ("Empréstimos E Financiamentos A Longo Prazo", "fcf_emprestimos"),
    ("Capital Social", "fcf_capital"),
    ("Capital Social Subscrito", "fcf_capital"),
]


# Pattern-based overrides applied AFTER subtree inheritance. Each
# entry is (substring, cashflow_category). Substring matches the
# account name case-insensitively; the override only writes when the
# leaf's resolved cashflow_category differs from the target. This is
# how we route empregado-related leaves out of the
# fco_pagamentos_fornecedores default bucket on Despesas
# Operacionais.
PATTERN_OVERRIDES: List[Tuple[str, str]] = [
    # ---- Empregados ----
    ("salário", "fco_pagamentos_empregados"),
    ("salarios", "fco_pagamentos_empregados"),
    ("remuneração", "fco_pagamentos_empregados"),
    ("remuneracao", "fco_pagamentos_empregados"),
    ("inss", "fco_pagamentos_empregados"),
    ("fgts", "fco_pagamentos_empregados"),
    ("vale refeição", "fco_pagamentos_empregados"),
    ("vale transporte", "fco_pagamentos_empregados"),
    ("vale alimentação", "fco_pagamentos_empregados"),
    ("plano de saúde", "fco_pagamentos_empregados"),
    ("plano de saude", "fco_pagamentos_empregados"),
    ("pró-labore", "fco_pagamentos_empregados"),
    ("pro-labore", "fco_pagamentos_empregados"),
    ("dissídio", "fco_pagamentos_empregados"),
    ("dissidio", "fco_pagamentos_empregados"),
    ("férias", "fco_pagamentos_empregados"),
    ("ferias", "fco_pagamentos_empregados"),
    ("13º salário", "fco_pagamentos_empregados"),
    ("13o salário", "fco_pagamentos_empregados"),
    ("rescisão", "fco_pagamentos_empregados"),
    ("rescisao", "fco_pagamentos_empregados"),
    ("inss/irrf", "fco_pagamentos_empregados"),

    # ---- Indirect taxes ----
    ("icms", "fco_impostos_indiretos"),
    ("pis ", "fco_impostos_indiretos"),
    ("pis a", "fco_impostos_indiretos"),
    ("pis/cofins", "fco_impostos_indiretos"),
    ("cofins", "fco_impostos_indiretos"),
    ("ipi ", "fco_impostos_indiretos"),
    ("ipi a", "fco_impostos_indiretos"),
    ("iss ", "fco_impostos_indiretos"),
    ("iss a", "fco_impostos_indiretos"),
    ("difal", "fco_impostos_indiretos"),

    # ---- Income taxes ----
    ("irpj", "fco_imposto_renda"),
    ("csll", "fco_imposto_renda"),
    ("irrf sobre aplicações", "fco_imposto_renda"),
    ("irrf sobre aplicacoes", "fco_imposto_renda"),

    # ---- Interest / banking ----
    ("rendimento", "fco_juros"),
    ("juros", "fco_juros"),
    ("tarifa banc", "fco_juros"),
    ("tarifas banc", "fco_juros"),
    ("variação monet", "fco_juros"),
    ("variacao monet", "fco_juros"),

    # ---- Investments (override for accounts under operating subtree) ----
    ("saldo do principal aplicado", "fci_investimentos_financeiros"),

    # ---- Dividends / JCP ----
    ("dividendos", "fcf_dividendos_jcp"),
    ("juros sobre capital próprio", "fcf_dividendos_jcp"),
    ("juros sobre capital proprio", "fcf_dividendos_jcp"),
    (" jcp", "fcf_dividendos_jcp"),
]


class Command(BaseCommand):
    help = (
        "Apply cashflow_category baseline to a tenant's chart of accounts. "
        "Idempotent; supports --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what would change without writing anything.",
        )
        parser.add_argument(
            "--tenant", default="evolat",
            help="Tenant subdomain to target (default: evolat).",
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]
        sub = opts["tenant"]

        try:
            company = Company.objects.get(subdomain=sub)
        except Company.DoesNotExist:
            raise CommandError(f"No tenant with subdomain={sub!r}")

        # Validate enum values up front -- a typo would silently
        # apply an invalid value otherwise.
        for _, cf in SUBTREE_ANCHORS:
            self._validate(cf)
        for _, cf in PATTERN_OVERRIDES:
            self._validate(cf)

        self.stdout.write(self.style.NOTICE(
            f"== Cashflow tagger for tenant={sub} (dry_run={dry_run}) =="
        ))

        # Pull every account once so we can do name lookups and
        # name-pattern scans without N queries.
        accounts = list(Account.objects.filter(company=company))
        by_name: dict[str, list[Account]] = {}
        for a in accounts:
            by_name.setdefault(a.name, []).append(a)

        changes: list[tuple[Account, str | None, str]] = []

        # ---- Pass 1: subtree anchors ----
        # Each anchor sets its own ``cashflow_category``; descendants
        # inherit via ``effective_cashflow_category``.
        for name, cf in SUBTREE_ANCHORS:
            matches = by_name.get(name, [])
            if not matches:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP anchor {name!r} -- not found"
                ))
                continue
            for acc in matches:
                if acc.cashflow_category == cf:
                    continue
                if acc.cashflow_category and acc.cashflow_category != cf:
                    self.stdout.write(self.style.WARNING(
                        f"  CONFLICT {acc.name!r}: explicit "
                        f"{acc.cashflow_category!r} overrides anchor "
                        f"{cf!r} -- skipping"
                    ))
                    continue
                changes.append((acc, acc.cashflow_category, cf))

        # ---- Pass 2: pattern overrides ----
        # Walk every account; if the name contains a pattern keyword
        # AND the resolved (effective) cashflow_category differs from
        # the override target, set ``cashflow_category`` directly on
        # the leaf.
        from accounting.services.taxonomy_resolver import (
            effective_cashflow_category,
        )
        for acc in accounts:
            lname = (acc.name or "").lower()
            hit: Optional[str] = None
            for needle, cf in PATTERN_OVERRIDES:
                if needle in lname:
                    hit = cf
                    break  # first-match wins; ordering matters
            if not hit:
                continue
            current_eff = effective_cashflow_category(acc)
            if current_eff == hit:
                continue
            # Only set if the pattern truly differs from inherited.
            # Skip if operator already set an explicit override that
            # matches our target (idempotence).
            if acc.cashflow_category == hit:
                continue
            changes.append((acc, acc.cashflow_category, hit))

        # ---- Report ----
        if not changes:
            self.stdout.write(self.style.SUCCESS("No changes needed."))
            return

        self.stdout.write(self.style.NOTICE(f"\nPlanned changes ({len(changes)}):"))
        for acc, current, desired in changes:
            # ASCII-only output: Windows cp1252 stdout chokes on
            # non-Latin glyphs (∅ / →) when the operator runs the
            # command from a stock CMD prompt. We use plain "(none)"
            # and "->" so the script works in every shell.
            current_label = current if current else "(none)"
            self.stdout.write(
                f"  [{acc.id:>5}] {acc.name!r:.50}  "
                f"{current_label:>32} -> {desired}"
            )

        if dry_run:
            self.stdout.write(self.style.NOTICE("\n--dry-run; no writes."))
            return

        with transaction.atomic():
            for acc, _, desired in changes:
                acc.cashflow_category = desired
                acc.save(update_fields=["cashflow_category"])
        self.stdout.write(self.style.SUCCESS(
            f"\nApplied {len(changes)} change(s)."
        ))

    def _validate(self, cf: str | None):
        if cf is None:
            return
        if cf not in CASHFLOW_CATEGORY_VALUES:
            raise CommandError(
                f"Invalid cashflow_category {cf!r}. "
                f"Allowed: {sorted(CASHFLOW_CATEGORY_VALUES)}"
            )
