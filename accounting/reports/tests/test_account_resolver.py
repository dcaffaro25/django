"""Database-backed tests for ``AccountResolver``.

The resolver was historically broken on ``path_contains``: ``Account``
exposes ``get_path()`` as a Python method, not a stored field, so the
old ``Q(path__icontains=...)`` filter raised ``FieldError`` on every
call. The error was being swallowed by ``_hydrate_account_ids``'s
catch-all, leaving codeless tenants (e.g. Evolat — every account_code
is null/"0", every line has to use path_contains) silently producing
empty reports.

These tests cover:
  * ``path_contains`` matches against the in-Python computed path.
  * ``path_contains`` returning empty correctly resolves to no rows
    (regression: an earlier fix produced "everything" because Q() is
    Django's identity).
  * ``code_prefix`` still works.
  * Combined selectors (path + code_prefix) compose by OR.

We use ``TestCase`` so the assertion fixtures roll back per-test.
"""
from __future__ import annotations

from django.test import TestCase

import datetime as dt

from accounting.models import Account, Currency
from accounting.reports.services.document_schema import AccountsSelector
from accounting.reports.services.intelligence import AccountResolver
from multitenancy.models import Company


class AccountResolverTests(TestCase):
    """Real-DB coverage for ``AccountResolver.resolve``."""

    @classmethod
    def setUpTestData(cls):
        # Minimal multi-level chart, mixing coded + uncoded accounts so
        # the same fixtures cover both Dat-Baby (coded) and Evolat
        # (codeless) shapes.
        cls.company = Company.objects.create(name="ResolverTests Co", subdomain="resolverco")
        # Account model NOT-NULLs ``currency`` and ``balance_date``;
        # provide a minimal Currency fixture and reuse it across the chart.
        cls.brl, _ = Currency.objects.get_or_create(
            code="BRL", defaults={"name": "Real", "symbol": "R$"},
        )
        _common = dict(
            balance=0,
            balance_date=dt.date(2025, 1, 1),
            currency=cls.brl,
        )

        # Top-level: Ativo (no code), Resultado (no code)
        cls.ativo = Account.objects.create(
            company=cls.company, name="Ativo", account_direction=1,
            account_code=None, level=0, **_common,
        )
        cls.resultado = Account.objects.create(
            company=cls.company, name="Resultado", account_direction=1,
            account_code=None, level=0, **_common,
        )

        # Child of Ativo: "Caixa" (codeless)
        cls.caixa = Account.objects.create(
            company=cls.company, name="Caixa", parent=cls.ativo,
            account_direction=1, account_code=None, level=1, **_common,
        )
        # Two leaves under Caixa
        cls.itau = Account.objects.create(
            company=cls.company, name="Itaú", parent=cls.caixa,
            account_direction=1, account_code=None, level=2, **_common,
        )
        cls.bb = Account.objects.create(
            company=cls.company, name="Banco do Brasil", parent=cls.caixa,
            account_direction=1, account_code=None, level=2, **_common,
        )

        # Coded branch under Resultado (mimics Dat-Baby): codes 4.01 / 4.02
        cls.receitas = Account.objects.create(
            company=cls.company, name="Receitas", parent=cls.resultado,
            account_direction=1, account_code="4", level=1, **_common,
        )
        cls.vendas = Account.objects.create(
            company=cls.company, name="Vendas", parent=cls.receitas,
            account_direction=1, account_code="4.01", level=2, **_common,
        )
        cls.servicos = Account.objects.create(
            company=cls.company, name="Serviços", parent=cls.receitas,
            account_direction=1, account_code="4.02", level=2, **_common,
        )

    # --- path_contains: the previously broken path ------------------------

    def test_path_contains_matches_via_in_memory_walk(self):
        """``path_contains: "Caixa"`` should hit Caixa + its descendants
        because the resolver computes paths from the parent chain."""
        resolver = AccountResolver(company_id=self.company.id)
        # Use include_descendants=False so we test the raw match — not the
        # MPTT expansion.
        sel = AccountsSelector(path_contains="Caixa", include_descendants=False)
        result = resolver.resolve(sel)
        ids = sorted(a.id for a in result)
        # The path of itau is "Ativo > Caixa > Itaú", the path of bb
        # is "Ativo > Caixa > Banco do Brasil", and Caixa itself's
        # path is "Ativo > Caixa". All three contain "Caixa".
        self.assertEqual(ids, sorted([self.caixa.id, self.itau.id, self.bb.id]))

    def test_path_contains_is_case_insensitive(self):
        """Matches on lowercase haystack so operator typing
        ``path_contains: "ATIVO"`` still hits the Ativo subtree."""
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector(path_contains="ATIVO", include_descendants=False)
        result = resolver.resolve(sel)
        ids = {a.id for a in result}
        # Every account under Ativo is included — that's 4 (ativo + caixa + itau + bb).
        # The resultado-rooted accounts must NOT match.
        self.assertIn(self.ativo.id, ids)
        self.assertIn(self.caixa.id, ids)
        self.assertIn(self.itau.id, ids)
        self.assertIn(self.bb.id, ids)
        self.assertNotIn(self.resultado.id, ids)
        self.assertNotIn(self.vendas.id, ids)

    def test_path_contains_no_match_returns_empty(self):
        """Regression test: an earlier fix added the path-id set to the
        Q-OR only when non-empty, which left ``filters = Q()`` (the
        identity) and made the resolver return EVERY account in the
        company. The fix forces an empty ``Q(id__in=[])`` so no rows
        match. Without this guard, codeless tenants would see every
        line in their AI-generated report ballooned to the entire CoA.
        """
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector(path_contains="DoesNotExistAnywhere", include_descendants=False)
        result = resolver.resolve(sel)
        self.assertEqual(result, [])

    # --- code_prefix: the existing happy path ----------------------------

    def test_code_prefix_matches_descendants_by_string_startswith(self):
        """The original behaviour — confirms the path_contains fix
        didn't accidentally break code_prefix."""
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector(code_prefix="4.0", include_descendants=False)
        result = resolver.resolve(sel)
        ids = {a.id for a in result}
        self.assertEqual(ids, {self.vendas.id, self.servicos.id})

    # --- combined selectors --------------------------------------------

    def test_path_and_code_prefix_compose_via_OR(self):
        """``path_contains`` and ``code_prefix`` are unioned, not
        intersected — operator who wants "everything under Caixa OR
        coded as 4.01" gets the union of both sets."""
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector(
            path_contains="Caixa", code_prefix="4.01",
            include_descendants=False,
        )
        result = resolver.resolve(sel)
        ids = {a.id for a in result}
        # Caixa subtree (caixa, itau, bb) + 4.01 (vendas).
        self.assertEqual(
            ids,
            {self.caixa.id, self.itau.id, self.bb.id, self.vendas.id},
        )

    # --- caching ------------------------------------------------------

    def test_repeated_resolve_uses_pattern_cache(self):
        """A second call with the same selector should not hit the DB
        twice. We're not asserting on connection counts (fragile under
        Django's connection wrappers); we're asserting that the same
        list object comes back, which is observable proof the cache
        served the second call."""
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector(path_contains="Caixa", include_descendants=False)
        first = resolver.resolve(sel)
        second = resolver.resolve(sel)
        self.assertIs(first, second)

    def test_resolve_none_returns_empty(self):
        """``selector=None`` is a no-op (matches the existing API
        contract). Defensive — callers that pass None shouldn't blow
        up."""
        resolver = AccountResolver(company_id=self.company.id)
        self.assertEqual(resolver.resolve(None), [])

    def test_empty_selector_returns_empty(self):
        """A selector with every field None/empty is also a no-op —
        explicit zero, not "match everything". Documented contract."""
        resolver = AccountResolver(company_id=self.company.id)
        sel = AccountsSelector()  # all fields default
        self.assertEqual(resolver.resolve(sel), [])
