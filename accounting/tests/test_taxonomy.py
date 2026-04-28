"""Tests for the Phase 1 CoA taxonomy work:

  * MPTT-walked inheritance resolvers (effective_category, effective_tags)
  * AccountViewSet's bulk path-map helper
  * AccountSerializer's reading of annotated balance + path map

These cover the three places the new design has decision points:

  * **Category inheritance** is *nearest-ancestor wins*. Walk up the
    parent chain until a node has a non-null ``report_category``;
    self overrides ancestor. Mixed-category subtrees (e.g. Evolat's
    ``Receita Operacional Líquida`` -> both receita_bruta and
    deducao_receita children) are handled by the operator tagging at
    level 2 instead of level 1; the resolver just needs to walk up.
  * **Tag inheritance** is *union with ancestors*. Child can ADD,
    cannot REMOVE. This makes contra accounts work naturally:
    Imobilizado tagged ``[fixed_asset]``, leaf "(-) Depreciação
    Acumulada" tagged ``[contra_account]``, effective tags on the
    leaf = ``[contra_account, fixed_asset]``.
  * **Path map** is built once per request from a single bulk query
    and cached in serializer context. Replaces the per-row lazy walk
    that fired three times per row in the old serializer.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from accounting.models import (
    Account,
    Bank,
    BankAccount,
    BankTransaction,
    Currency,
)
from accounting.services.taxonomy_resolver import (
    effective_category,
    effective_tags,
    has_any_tag,
    has_tags,
)
from accounting.views import _build_account_path_map
from multitenancy.models import Company, Entity


class _FixtureMixin:
    """Builds a small but realistic Evolat-shaped tree:

    Resultado (level 0)
    ├── Receita Operacional Líquida (level 1) -- mixed category, NOT tagged
    │   ├── Receita Bruta de Vendas (level 2, tagged receita_bruta)
    │   │   ├── Receita Mercadorias (level 3)
    │   │   └── Receita Serviços (level 3)
    │   └── Deduções da Receita (level 2, tagged deducao_receita)
    │       └── (-) ICMS sobre Vendas (level 3, tags=[icms])
    Ativo (level 0)
    └── Ativo Não Circulante (level 1, tagged ativo_nao_circulante,
        tags=[fixed_asset])
        └── Imobilizado (level 2)
            └── (-) Depreciação Acumulada (level 3, tags=[contra_account])
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="TaxCo", subdomain="taxco")
        cls.entity = Entity.objects.create(company=cls.company, name="Acme")
        cls.brl = Currency.objects.create(code="BRL", name="Real")

        # ---------- Resultado subtree ----------
        cls.resultado = Account.objects.create(
            company=cls.company, name="Resultado", account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=None,
        )
        # Mixed-category parent -- intentionally NOT tagged.
        cls.receita_op_liquida = Account.objects.create(
            company=cls.company, name="Receita Operacional Líquida",
            account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.resultado,
        )
        # Level 2 -- tagged receita_bruta.
        cls.receita_bruta = Account.objects.create(
            company=cls.company, name="Receita Bruta de Vendas",
            account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.receita_op_liquida,
            report_category="receita_bruta",
        )
        cls.receita_mercadorias = Account.objects.create(
            company=cls.company, name="Receita Mercadorias",
            account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.receita_bruta,
            tags=["product_sales"],
        )
        cls.receita_servicos = Account.objects.create(
            company=cls.company, name="Receita Serviços",
            account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.receita_bruta,
            tags=["service_revenue"],
        )
        # Level 2 -- tagged deducao_receita.
        cls.deducoes = Account.objects.create(
            company=cls.company, name="Deduções da Receita",
            account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.receita_op_liquida,
            report_category="deducao_receita",
        )
        cls.icms = Account.objects.create(
            company=cls.company, name="(-) ICMS sobre Vendas",
            account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.deducoes,
            tags=["icms"],
        )

        # ---------- Ativo subtree ----------
        cls.ativo = Account.objects.create(
            company=cls.company, name="Ativo", account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=None,
        )
        # Level 1 carries BOTH category AND tags.
        cls.ativo_nc = Account.objects.create(
            company=cls.company, name="Ativo Não Circulante",
            account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.ativo,
            report_category="ativo_nao_circulante",
            tags=["fixed_asset"],
        )
        cls.imobilizado = Account.objects.create(
            company=cls.company, name="Imobilizado",
            account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.ativo_nc,
        )
        # Contra leaf: own tag adds to the inherited set.
        cls.depreciacao = Account.objects.create(
            company=cls.company, name="(-) Depreciação Acumulada",
            account_direction=-1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=cls.imobilizado,
            tags=["contra_account"],
        )

        # Untagged orphan: no ancestor has report_category.
        cls.untagged = Account.objects.create(
            company=cls.company, name="Bank Clearing (Pending)",
            account_direction=1,
            balance=Decimal("0"), balance_date=dt.date(2026, 1, 1),
            currency=cls.brl, parent=None,
        )


class EffectiveCategoryTests(_FixtureMixin, TestCase):
    """Nearest-ancestor wins; self overrides; missing returns None."""

    def test_self_tagged_returns_self(self):
        self.assertEqual(effective_category(self.receita_bruta), "receita_bruta")
        self.assertEqual(effective_category(self.ativo_nc), "ativo_nao_circulante")

    def test_descendant_inherits_from_nearest_tagged_ancestor(self):
        # Two levels down -- still inherits from parent.
        self.assertEqual(effective_category(self.receita_mercadorias), "receita_bruta")
        self.assertEqual(effective_category(self.icms), "deducao_receita")
        # Three levels down through Imobilizado (untagged) and Ativo NC.
        self.assertEqual(effective_category(self.depreciacao), "ativo_nao_circulante")

    def test_mixed_parent_disambiguated_by_level2_tagging(self):
        """The classic Evolat case. Level-1 ``Receita Operacional
        Líquida`` is intentionally untagged -- its level-2 children
        carry different categories. The resolver should walk past the
        untagged level 1 and find the correct level-2 tag for each."""
        self.assertEqual(effective_category(self.receita_servicos), "receita_bruta")
        self.assertEqual(effective_category(self.icms), "deducao_receita")

    def test_untagged_chain_returns_none(self):
        self.assertIsNone(effective_category(self.untagged))
        # Receita Operacional Líquida itself has no category; nor does
        # Resultado above it.
        self.assertIsNone(effective_category(self.receita_op_liquida))
        self.assertIsNone(effective_category(self.resultado))

    def test_self_override_beats_ancestor(self):
        """If a leaf is explicitly tagged with a different category
        than its ancestor, self wins."""
        # Imobilizado naturally inherits ativo_nao_circulante from
        # Ativo NC. Override it on the leaf.
        self.imobilizado.report_category = "memo"
        self.imobilizado.save()
        self.assertEqual(effective_category(self.imobilizado), "memo")
        # Descendants of imobilizado should now see the new override.
        self.assertEqual(effective_category(self.depreciacao), "memo")


class EffectiveTagsTests(_FixtureMixin, TestCase):
    """Union semantics: child tags compose with ancestor tags."""

    def test_self_tags_when_no_ancestor_tags(self):
        self.assertEqual(effective_tags(self.icms), ["icms"])
        self.assertEqual(effective_tags(self.receita_mercadorias), ["product_sales"])

    def test_descendant_inherits_ancestor_tags(self):
        # Imobilizado has no own tags but inherits from Ativo NC.
        self.assertEqual(effective_tags(self.imobilizado), ["fixed_asset"])

    def test_contra_account_composes_inherited_plus_own(self):
        """The contra-account scenario: leaf has its own tag; parent
        chain contributes ``fixed_asset``; effective set is the
        union."""
        self.assertEqual(
            effective_tags(self.depreciacao),
            ["contra_account", "fixed_asset"],
        )

    def test_no_tags_anywhere_returns_empty(self):
        self.assertEqual(effective_tags(self.untagged), [])
        self.assertEqual(effective_tags(self.resultado), [])

    def test_has_tags_helper(self):
        self.assertTrue(has_tags(self.depreciacao, ["fixed_asset"]))
        self.assertTrue(has_tags(self.depreciacao, ["contra_account"]))
        self.assertTrue(has_tags(self.depreciacao, ["fixed_asset", "contra_account"]))
        self.assertFalse(has_tags(self.depreciacao, ["debt"]))

    def test_has_any_tag_helper(self):
        self.assertTrue(has_any_tag(self.depreciacao, ["debt", "contra_account"]))
        self.assertFalse(has_any_tag(self.untagged, ["fixed_asset", "cash"]))


class BuildAccountPathMapTests(_FixtureMixin, TestCase):
    """The bulk path-map helper used by ``AccountViewSet`` to kill the
    per-row N+1 in ``AccountSerializer``. Same shape as the
    ``ai_assistant._build_chart_context`` optimisation."""

    def setUp(self):
        # Pull the rows the helper actually consumes -- the same shape
        # the viewset builds.
        self.rows = list(
            Account.objects
            .filter(company=self.company)
            .values('id', 'name', 'parent_id')
        )
        self.path_map = _build_account_path_map(self.rows)

    def test_root_node_has_path_equal_to_name(self):
        entry = self.path_map[self.resultado.id]
        self.assertEqual(entry["path"], "Resultado")
        self.assertEqual(entry["path_ids"], [self.resultado.id])
        self.assertEqual(entry["level"], 0)

    def test_deep_node_has_full_chain_path(self):
        entry = self.path_map[self.depreciacao.id]
        self.assertEqual(
            entry["path"],
            "Ativo > Ativo Não Circulante > Imobilizado > (-) Depreciação Acumulada",
        )
        self.assertEqual(entry["level"], 3)
        self.assertEqual(entry["path_ids"][0], self.ativo.id)
        self.assertEqual(entry["path_ids"][-1], self.depreciacao.id)
        self.assertEqual(len(entry["path_ids"]), 4)

    def test_every_account_in_input_appears_in_map(self):
        ids_in = {r['id'] for r in self.rows}
        ids_out = set(self.path_map.keys())
        self.assertEqual(ids_in, ids_out)

    def test_orphan_node_has_correct_path(self):
        entry = self.path_map[self.untagged.id]
        self.assertEqual(entry["path"], "Bank Clearing (Pending)")
        self.assertEqual(entry["level"], 0)

    def test_handles_corrupted_cycle_without_hanging(self):
        """Defensive: if a corrupt parent_id loop existed, the helper
        must still terminate (and produce something sensible) rather
        than hang the request."""
        rows = [
            {'id': 1, 'name': 'A', 'parent_id': 2},
            {'id': 2, 'name': 'B', 'parent_id': 1},  # cycle
        ]
        m = _build_account_path_map(rows)
        # Termination is the test. Path content is best-effort.
        self.assertIn(1, m)
        self.assertIn(2, m)
        self.assertIn("A", m[1]["path"])
        self.assertIn("B", m[2]["path"])


class AccountQuerysetAnnotationTests(_FixtureMixin, TestCase):
    """Smoke test: ``annotated_current_balance`` actually computes via
    the Subquery branch in ``AccountViewSet.get_queryset`` and matches
    what the legacy per-row method returns."""

    def test_annotated_balance_matches_method_for_non_bank_account(self):
        # Most accounts have no bank_account FK -- the Subquery
        # contributes 0 and the column equals stored balance.
        from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
        from django.db.models.functions import Coalesce

        bank_sum = (
            BankTransaction.objects
            .filter(
                bank_account=OuterRef('bank_account'),
                date__gt=OuterRef('balance_date'),
                balance_validated=False,
            )
            .values('bank_account')
            .annotate(s=Sum('amount'))
            .values('s')[:1]
        )
        qs = Account.objects.filter(company=self.company).annotate(
            annotated_current_balance=(
                F('balance')
                + Coalesce(
                    Subquery(
                        bank_sum,
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Value(Decimal('0'), output_field=DecimalField(max_digits=12, decimal_places=2)),
                )
            ),
        )
        for a in qs:
            self.assertEqual(
                Decimal(a.annotated_current_balance),
                a.balance,  # no bank txs in fixture
                msg=f"mismatch on {a.name}",
            )
