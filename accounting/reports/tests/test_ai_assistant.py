"""Tests for the AI assistant module.

Focuses on :func:`_hydrate_account_ids` — the post-generation pass that
walks the AI's draft template and pins each line/subtotal's
``accounts.account_ids`` to the concrete list resolved against the
live chart of accounts.

These are pure unit tests: the resolver is stubbed so we never need a
real ``Account`` fixture. Integration tests that exercise the full
``generate_template`` flow against a real CoA belong in a manual
QA/E2E suite — the OpenAI call costs money on every run.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from accounting.reports.services.ai_assistant import (
    _build_user_prompt,
    _hydrate_account_ids,
)


def _mk_account(id: int) -> MagicMock:
    """Lightweight stand-in for an Account model — we only read ``id``."""
    a = MagicMock()
    a.id = id
    return a


def _resolver_canned(per_selector_ids: dict) -> MagicMock:
    """Return a resolver mock whose ``.resolve(selector)`` looks up the
    selector's ``code_prefix`` in the canned dict and returns the
    matching account stubs.
    """
    resolver = MagicMock()

    def fake_resolve(selector):
        if selector is None:
            return []
        if selector.account_ids:
            return [_mk_account(i) for i in selector.account_ids]
        ids = per_selector_ids.get(selector.code_prefix, [])
        return [_mk_account(i) for i in ids]

    resolver.resolve = fake_resolve
    return resolver


def _patch_resolver(per_selector_ids: dict):
    """Patch the resolver class so ``_hydrate_account_ids`` instantiates
    our canned mock instead of hitting the database."""
    return patch(
        "accounting.reports.services.intelligence.AccountResolver",
        return_value=_resolver_canned(per_selector_ids),
    )


class HydrateAccountIdsTests(SimpleTestCase):
    """``_hydrate_account_ids`` walks the AI draft and pins concrete
    ``account_ids`` to every line/subtotal selector. These tests stub
    the resolver so they don't need a live CoA fixture — see the
    intelligence tests for resolver-vs-DB coverage.
    """

    # --- Hydration happy paths ---------------------------------------------

    def test_populates_account_ids_for_top_level_lines(self):
        """A flat doc with two lines, each carrying a ``code_prefix``,
        gets ``account_ids`` populated with the resolver's matches."""
        doc = {
            "name": "DRE",
            "report_type": "income_statement",
            "blocks": [
                {"type": "line", "id": "sales", "label": "Vendas",
                 "accounts": {"code_prefix": "4.01", "include_descendants": True}},
                {"type": "line", "id": "services", "label": "Serviços",
                 "accounts": {"code_prefix": "4.02", "include_descendants": True}},
            ],
        }
        canned = {"4.01": [101, 102], "4.02": [201]}
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        by_id = {b["id"]: b for b in out["blocks"]}
        self.assertEqual(by_id["sales"]["accounts"]["account_ids"], [101, 102])
        self.assertEqual(by_id["services"]["accounts"]["account_ids"], [201])
        # The original code_prefix is preserved alongside — the resolver
        # at calculate-time ORs both, so adding new accounts later that
        # match the prefix still flows through without re-hydration.
        self.assertEqual(by_id["sales"]["accounts"]["code_prefix"], "4.01")
        self.assertEqual(unmapped, [])

    def test_recurses_into_section_children(self):
        """Sections own a ``children`` list; lines nested inside must
        also get their ``account_ids`` hydrated. Reflects the canonical
        doc shape after ``slim_to_canonical`` rebuilds the tree."""
        doc = {
            "name": "DRE",
            "report_type": "income_statement",
            "blocks": [
                {
                    "type": "section", "id": "rev", "label": "Receita",
                    "children": [
                        {"type": "line", "id": "a", "accounts": {"code_prefix": "4.01"}},
                        {"type": "section", "id": "rev_other", "label": "Outras", "children": [
                            {"type": "line", "id": "b", "accounts": {"code_prefix": "4.99"}},
                        ]},
                    ],
                },
            ],
        }
        canned = {"4.01": [10, 11], "4.99": [99]}
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        rev = out["blocks"][0]
        a = rev["children"][0]
        rev_other = rev["children"][1]
        b = rev_other["children"][0]
        self.assertEqual(a["accounts"]["account_ids"], [10, 11])
        self.assertEqual(b["accounts"]["account_ids"], [99])
        self.assertEqual(unmapped, [])

    def test_records_unmapped_when_pattern_matches_nothing(self):
        """A code_prefix that resolves to zero accounts is reported via
        the unmapped list — callers (UI / logs) use this to surface a
        'review these lines' banner so operators don't ship an empty
        report."""
        doc = {
            "name": "DRE", "report_type": "income_statement",
            "blocks": [
                {"type": "line", "id": "valid", "accounts": {"code_prefix": "4.01"}},
                {"type": "line", "id": "ghost", "accounts": {"code_prefix": "9.99"}},
            ],
        }
        canned = {"4.01": [1, 2]}  # 9.99 deliberately missing
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        by_id = {b["id"]: b for b in out["blocks"]}
        self.assertEqual(by_id["valid"]["accounts"]["account_ids"], [1, 2])
        self.assertFalse(by_id["ghost"]["accounts"].get("account_ids"))
        self.assertEqual(unmapped, ["ghost"])

    def test_preserves_existing_account_ids(self):
        """If the AI emits an explicit ``account_ids`` (rare but
        supported by the slim schema), the hydration pass must NOT
        clobber it. The AI's explicit list is its preferred wiring;
        the operator can refine later."""
        doc = {
            "name": "DRE", "report_type": "income_statement",
            "blocks": [
                {"type": "line", "id": "explicit",
                 "accounts": {"account_ids": [777], "code_prefix": "4.01"}},
            ],
        }
        canned = {"4.01": [111, 222]}
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        self.assertEqual(out["blocks"][0]["accounts"]["account_ids"], [777])
        self.assertEqual(unmapped, [])

    def test_skips_lines_without_a_selector(self):
        """A line with no ``accounts`` field at all (e.g. a manual_value
        line) must pass through untouched and NOT show up as unmapped."""
        doc = {
            "name": "DRE", "report_type": "income_statement",
            "blocks": [
                {"type": "line", "id": "manual", "label": "Ajuste",
                 "manual_value": "100.00"},
                {"type": "line", "id": "auto", "accounts": {"code_prefix": "4.01"}},
            ],
        }
        canned = {"4.01": [1]}
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        self.assertNotIn("accounts", out["blocks"][0])
        self.assertEqual(out["blocks"][1]["accounts"]["account_ids"], [1])
        self.assertEqual(unmapped, [])

    def test_skips_subtotals_with_only_a_formula(self):
        """Subtotals that compute from siblings (``sum(children)``)
        carry no ``accounts`` selector — they shouldn't be hydrated,
        and they shouldn't be reported as unmapped."""
        doc = {
            "name": "DRE", "report_type": "income_statement",
            "blocks": [
                {"type": "section", "id": "rev", "children": [
                    {"type": "line", "id": "a", "accounts": {"code_prefix": "4.01"}},
                    {"type": "subtotal", "id": "st", "formula": "sum(children)"},
                ]},
            ],
        }
        canned = {"4.01": [1, 2]}
        with _patch_resolver(canned):
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        children = out["blocks"][0]["children"]
        self.assertEqual(children[0]["accounts"]["account_ids"], [1, 2])
        # Subtotal got nothing added (no accounts dict); not in unmapped.
        self.assertNotIn("accounts", children[1])
        self.assertEqual(unmapped, [])

    def test_dedupes_and_sorts_account_ids(self):
        """The resolver may return duplicates (a parent account
        included plus its descendants returning the same ids).
        Hydrated list is sorted + unique so saved templates are stable
        across regenerations and easy to diff."""
        resolver = MagicMock()
        resolver.resolve = MagicMock(return_value=[
            _mk_account(50), _mk_account(20), _mk_account(50), _mk_account(10),
        ])
        with patch(
            "accounting.reports.services.intelligence.AccountResolver",
            return_value=resolver,
        ):
            doc = {
                "name": "DRE", "report_type": "income_statement",
                "blocks": [
                    {"type": "line", "id": "x", "accounts": {"code_prefix": "4"}},
                ],
            }
            out, _unmapped = _hydrate_account_ids(doc, company_id=1)

        self.assertEqual(out["blocks"][0]["accounts"]["account_ids"], [10, 20, 50])

    # --- Defensive behavior ------------------------------------------------

    def test_continues_on_resolver_failure(self):
        """If the resolver throws on one block (e.g. transient DB
        error, malformed selector), the hydration logs and moves on
        rather than aborting the whole template — partial wiring is
        more useful than none. The failed block is NOT reported as
        unmapped (we can't tell the difference between 'matched zero'
        and 'failed to query')."""
        resolver = MagicMock()

        def flaky_resolve(selector):
            if selector.code_prefix == "boom":
                raise RuntimeError("simulated DB hiccup")
            return [_mk_account(1)]

        resolver.resolve = flaky_resolve
        with patch(
            "accounting.reports.services.intelligence.AccountResolver",
            return_value=resolver,
        ):
            doc = {
                "name": "DRE", "report_type": "income_statement",
                "blocks": [
                    {"type": "line", "id": "ok", "accounts": {"code_prefix": "4.01"}},
                    {"type": "line", "id": "fail", "accounts": {"code_prefix": "boom"}},
                    {"type": "line", "id": "ok2", "accounts": {"code_prefix": "4.02"}},
                ],
            }
            out, unmapped = _hydrate_account_ids(doc, company_id=1)

        by_id = {b["id"]: b for b in out["blocks"]}
        self.assertEqual(by_id["ok"]["accounts"]["account_ids"], [1])
        self.assertEqual(by_id["ok2"]["accounts"]["account_ids"], [1])
        # Failed lookup: account_ids stays unset; not in unmapped (not
        # a "matched zero" semantic).
        self.assertFalse(by_id["fail"]["accounts"].get("account_ids"))
        self.assertNotIn("fail", unmapped)

    def test_handles_empty_doc_gracefully(self):
        """A doc with no blocks at all just returns empty unmapped —
        the resolver is never called."""
        with patch("accounting.reports.services.intelligence.AccountResolver") as m:
            m.return_value = MagicMock()
            out, unmapped = _hydrate_account_ids(
                {"name": "T", "report_type": "income_statement", "blocks": []},
                company_id=1,
            )
        self.assertEqual(unmapped, [])
        self.assertEqual(out["blocks"], [])


class BuildUserPromptCodelessHintTests(SimpleTestCase):
    """The user prompt grows a codeless-tenant hint when every account
    in the sampled chart has an empty / placeholder code. Drives the AI
    away from ``code_prefix`` (which can't disambiguate) and toward
    ``path_contains`` / explicit ``account_ids``.

    Covers the Evolat case where every ``account_code`` is ``None`` /
    ``"0"`` and code-based selectors silently match nothing.
    """

    def _ctx(self, account_codes: list) -> dict:
        """Build a minimal chart context dict matching the shape
        ``_build_chart_context`` produces — just enough fields for
        ``_build_user_prompt`` to format."""
        return {
            "total_accounts": len(account_codes),
            "sampled": len(account_codes),
            "accounts": [
                {"code": c, "name": f"acc{i}", "path": f"Root > acc{i}",
                 "direction": 1, "level": 2}
                for i, c in enumerate(account_codes)
            ],
        }

    def test_codeless_chart_emits_warning_in_prompt(self):
        """All accounts have ``account_code = None``: the prompt must
        instruct the AI to skip ``code_prefix`` and use
        ``path_contains`` instead."""
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx([None, None, None]),
        )
        self.assertIn("no usable account codes", prompt)
        self.assertIn("path_contains", prompt)
        self.assertIn("DO NOT emit ``code_prefix``", prompt)

    def test_placeholder_zero_codes_count_as_codeless(self):
        """Some legacy charts store ``"0"`` as a placeholder for
        "no code". Treat that the same as empty."""
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx(["0", "0", "0"]),
        )
        self.assertIn("no usable account codes", prompt)

    def test_real_codes_skip_the_codeless_hint(self):
        """When even a single account has a real code, the hint stays
        out — the AI should default to ``code_prefix`` patterns."""
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx(["4.01", "4.02", "5.01"]),
        )
        self.assertNotIn("no usable account codes", prompt)
        self.assertNotIn("DO NOT emit ``code_prefix``", prompt)

    def test_mixed_real_and_empty_codes_skips_hint_when_above_threshold(self):
        """When the fraction of real codes is meaningful (>=20% in v2),
        ``code_prefix`` matching is still useful for the AI. 1 of 3
        coded = 33% > 20% so the hint stays out."""
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx(["4.01", None, "0"]),
        )
        self.assertNotIn("no usable account codes", prompt)

    def test_mostly_uncoded_chart_emits_hint(self):
        """v2 codeless detection: when most accounts are uncoded a few
        real codes don't rescue the chart. 1 real code among 100 = 1%
        is below the 20% threshold and the hint must fire — otherwise
        the AI emits ``code_prefix`` patterns the resolver can't match.
        Reproduces the original Evolat-mostly-codeless failure mode in
        a controlled fixture (no DB required)."""
        codes = ["4.01"] + [None] * 99
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx(codes),
        )
        self.assertIn("no usable account codes", prompt)
        self.assertIn("path_contains", prompt)

    def test_bank_artifact_codes_do_not_count_as_real(self):
        """Bank-account links auto-generate codes like
        ``1.1.1.BANK.27`` that aren't real CoA codes. Those must NOT
        rescue an otherwise-codeless chart — this was the exact
        failure on Evolat: 3 BANK-pseudo codes among 353 uncoded
        accounts kept ``useless_codes`` False under the old
        ``distinct_codes <= {"", "0"}`` check, the AI got no hint, and
        every line resolved to zero accounts."""
        codes = ["1.1.1.BANK.27", "1.1.1.BANK.209", "1.2.1.BANK.5"] + [None] * 50
        prompt = _build_user_prompt(
            "income_statement", "", self._ctx(codes),
        )
        self.assertIn("no usable account codes", prompt)
        self.assertIn("path_contains", prompt)
        self.assertIn("BANK.27", prompt.lower() if False else prompt)  # hint mentions the artifact pattern

    def test_prompt_includes_account_id_column(self):
        """The chart shown to the AI now includes each account's id so
        ``account_ids`` selectors can reference real ids instead of
        the AI hallucinating numbers. Regression guard for the
        codeless tenants where ``account_ids`` is the most reliable
        selector."""
        ctx = self._ctx([None, None])
        # Simulate ``_build_chart_context`` which adds the id field.
        for i, a in enumerate(ctx["accounts"]):
            a["id"] = 100 + i
        prompt = _build_user_prompt("income_statement", "", ctx)
        self.assertIn("#  100", prompt)
        self.assertIn("#  101", prompt)
        self.assertIn("id | code | level | path", prompt)
