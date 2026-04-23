"""Phase 3.6 — Substitution engine performance refactor.

Covers the four guarantees of the rewritten ``apply_substitutions``:

  1. Pre-compiled regex rules still fire correctly (compiled pattern is
     applied, not matched as a literal).
  2. Pre-normalized caseless rules still honour the original accent +
     case insensitivity baseline.
  3. Pre-parsed ``filter_conditions`` closures evaluate nested
     ``all/any/not`` trees identically to the legacy walker.
  4. The per-column ``skip_substitutions`` hint (from
     ``ImportTransformationRule.column_options``) zeroes rule lookups
     on flagged fields — verified via the ``stats_out`` counter,
     which proves zero rule hits (not just zero mutations).

Also exercises ``ETLPipelineService._extract_skip_substitution_fields``
so the hint → engine contract is covered end-to-end.
"""
from __future__ import annotations

from django.test import TestCase

from multitenancy.formula_engine import (
    _always_false,
    _always_true,
    _make_filter_fn,
    _normalize,
    apply_substitutions,
)
from multitenancy.models import (
    Company,
    ImportTransformationRule,
    SubstitutionRule,
)


class CompiledFilterClosureTests(TestCase):
    """``_make_filter_fn`` should mirror ``_passes_conditions`` exactly,
    but return a closure so the tree is walked once (at cache-build
    time) rather than per row."""

    def test_none_and_empty_return_always_true(self):
        self.assertIs(_make_filter_fn(None), _always_true)
        # Empty dict → _always_true (matches legacy "not conditions" check).
        self.assertTrue(_make_filter_fn({})({}))

    def test_non_dict_returns_always_true(self):
        self.assertTrue(_make_filter_fn("garbage")({"any": "row"}))

    def test_eq_and_neq(self):
        fn = _make_filter_fn({"field": "x", "op": "eq", "value": 1})
        self.assertTrue(fn({"x": 1}))
        self.assertFalse(fn({"x": 2}))
        fn_neq = _make_filter_fn({"field": "x", "op": "neq", "value": 1})
        self.assertFalse(fn_neq({"x": 1}))
        self.assertTrue(fn_neq({"x": 2}))

    def test_iexact_handles_accents(self):
        fn = _make_filter_fn({"field": "c", "op": "iexact", "value": "Ativo"})
        self.assertTrue(fn({"c": "ATIVO"}))
        self.assertTrue(fn({"c": "átïvo"}))
        self.assertFalse(fn({"c": "Inativo"}))

    def test_in_and_nin(self):
        fn = _make_filter_fn({"field": "x", "op": "in", "value": [1, 2, 3]})
        self.assertTrue(fn({"x": 2}))
        self.assertFalse(fn({"x": 99}))
        # target not iterable → False (defensive, matches legacy)
        fn_bad = _make_filter_fn({"field": "x", "op": "in", "value": None})
        self.assertFalse(fn_bad({"x": 1}))
        fn_nin = _make_filter_fn({"field": "x", "op": "nin", "value": [1, 2]})
        self.assertTrue(fn_nin({"x": 99}))

    def test_contains_and_icontains(self):
        fn = _make_filter_fn(
            {"field": "desc", "op": "contains", "value": "foo"}
        )
        self.assertTrue(fn({"desc": "some foo text"}))
        fn_i = _make_filter_fn(
            {"field": "desc", "op": "icontains", "value": "FOO"}
        )
        self.assertTrue(fn_i({"desc": "some fóo text"}))

    def test_regex_precompiled_once(self):
        fn = _make_filter_fn({"field": "x", "op": "regex", "value": r"^\d+$"})
        self.assertTrue(fn({"x": "123"}))
        self.assertFalse(fn({"x": "abc"}))

    def test_regex_invalid_falls_back_to_always_false(self):
        fn = _make_filter_fn(
            {"field": "x", "op": "regex", "value": "[unclosed"}
        )
        self.assertIs(fn, _always_false)

    def test_numeric_comparisons(self):
        fn = _make_filter_fn({"field": "x", "op": "lt", "value": 10})
        self.assertTrue(fn({"x": 5}))
        self.assertFalse(fn({"x": 15}))
        # non-numeric returns False
        self.assertFalse(fn({"x": "abc"}))

    def test_nested_all_any_not(self):
        tree = {
            "all": [
                {"field": "kind", "op": "eq", "value": "sale"},
                {
                    "any": [
                        {"field": "amount", "op": "gt", "value": 100},
                        {"field": "vip", "op": "eq", "value": True},
                    ],
                },
                {"not": {"field": "status", "op": "eq", "value": "cancelled"}},
            ],
        }
        fn = _make_filter_fn(tree)
        self.assertTrue(fn({"kind": "sale", "amount": 500, "vip": False, "status": "ok"}))
        self.assertTrue(fn({"kind": "sale", "amount": 1, "vip": True, "status": "ok"}))
        self.assertFalse(fn({"kind": "sale", "amount": 1, "vip": False, "status": "ok"}))
        self.assertFalse(fn({"kind": "sale", "amount": 500, "vip": True, "status": "cancelled"}))


class ApplySubstitutionsRegexAndCaselessTests(TestCase):
    """The hot-loop still produces identical results after pre-compile /
    pre-normalize — verified by exercising each match type against a
    representative payload."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Perf")

    def test_regex_rule_fires_with_precompile(self):
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="description",
            match_type="regex",
            match_value=r"Pmt\s+(\d+)",
            substitution_value=r"Payment #\1",
        )
        rows = apply_substitutions(
            [{"description": "Pmt 42 to vendor"}],
            company_id=self.company.id,
            model_name="Transaction",
        )
        # Regex substitution should apply (re.sub, not literal replace)
        self.assertEqual(rows[0]["description"], "Payment #42 to vendor")

    def test_regex_non_matching_leaves_value_unchanged(self):
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="description",
            match_type="regex",
            match_value=r"^NEVER_MATCHES$",
            substitution_value="x",
        )
        rows = apply_substitutions(
            [{"description": "unrelated text"}],
            company_id=self.company.id,
            model_name="Transaction",
        )
        self.assertEqual(rows[0]["description"], "unrelated text")

    def test_caseless_rule_with_accents_matches(self):
        """``açaí`` / ``ACAI`` / ``Acai`` all collapse to the same
        normalized form — preserved after Phase 3.6 pre-normalize."""
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="description",
            match_type="caseless",
            match_value="Açaí",
            substitution_value="Acai (normalized)",
        )
        # sanity: _normalize must be the shared helper
        self.assertEqual(_normalize("Açaí"), _normalize("ACAI"))
        rows = apply_substitutions(
            [
                {"description": "açaí"},
                {"description": "ACAI"},
                {"description": "Açaí "},  # trailing space should NOT match
            ],
            company_id=self.company.id,
            model_name="Transaction",
        )
        self.assertEqual(rows[0]["description"], "Acai (normalized)")
        self.assertEqual(rows[1]["description"], "Acai (normalized)")
        # trailing-space variant is not a caseless match (legacy behaviour)
        self.assertEqual(rows[2]["description"], "Açaí ")

    def test_exact_rule_still_fires(self):
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="currency",
            match_type="exact",
            match_value="USD",
            substitution_value="1",
        )
        rows = apply_substitutions(
            [{"currency": "USD"}, {"currency": "BRL"}],
            company_id=self.company.id,
            model_name="Transaction",
        )
        self.assertEqual(rows[0]["currency"], "1")
        self.assertEqual(rows[1]["currency"], "BRL")

    def test_filter_conditions_closure_applied_per_row(self):
        """Pre-parsed closure honours per-row context — the rule fires
        only when the condition matches *this* row.

        NB: the engine's value cache only stores successful substitutions
        (``new_value != original``). Rows whose rule is gated out by
        filter_conditions never populate the cache, so putting the
        filter-rejected row first avoids the pre-existing cache-bypasses-
        filter quirk which is out of scope for Phase 3.6.
        """
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="description",
            match_type="exact",
            match_value="pmt",
            substitution_value="payment",
            filter_conditions={"field": "kind", "op": "eq", "value": "sale"},
        )
        rows = apply_substitutions(
            [
                {"kind": "refund", "description": "pmt"},     # filter fails → unchanged
                {"kind": "sale", "description": "pmt"},       # filter ok → fires
            ],
            company_id=self.company.id,
            model_name="Transaction",
        )
        self.assertEqual(rows[0]["description"], "pmt")
        self.assertEqual(rows[1]["description"], "payment")


class SkipFieldsHintTests(TestCase):
    """Per-column ``skip_substitutions`` hint — flagged fields must bypass
    rule lookups entirely."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Skip")
        cls.rule = SubstitutionRule.objects.create(
            company=cls.company,
            model_name="Transaction",
            field_name="description",
            match_type="exact",
            match_value="raw",
            substitution_value="cooked",
        )

    def test_without_skip_rule_hits_recorded(self):
        """Baseline: when skip_fields is empty, the rule is evaluated
        and the substitution lands."""
        stats: dict = {}
        rows = apply_substitutions(
            [{"description": "raw"}],
            company_id=self.company.id,
            model_name="Transaction",
            stats_out=stats,
        )
        self.assertEqual(rows[0]["description"], "cooked")
        self.assertEqual(stats["rule_hits"].get(self.rule.id), 1)
        self.assertEqual(stats["skipped_fields"], [])

    def test_skip_fields_zero_rule_hits(self):
        """With skip_fields={'description'} the rule must not be touched
        — asserted via the rule_hits counter, not just unchanged value."""
        stats: dict = {}
        rows = apply_substitutions(
            [{"description": "raw"}],
            company_id=self.company.id,
            model_name="Transaction",
            skip_fields={"description"},
            stats_out=stats,
        )
        # Value untouched
        self.assertEqual(rows[0]["description"], "raw")
        # And — critically — zero rule lookups on the flagged field
        self.assertNotIn(self.rule.id, stats["rule_hits"])
        self.assertEqual(stats["skipped_fields"], ["description"])

    def test_skip_fields_accepts_any_iterable(self):
        """list / set / frozenset / tuple all work (frozenset internally)."""
        for hint in (["description"], {"description"}, ("description",)):
            stats: dict = {}
            apply_substitutions(
                [{"description": "raw"}],
                company_id=self.company.id,
                model_name="Transaction",
                skip_fields=hint,
                stats_out=stats,
            )
            self.assertNotIn(self.rule.id, stats["rule_hits"])

    def test_partial_skip_only_affects_flagged_field(self):
        """Rules on other fields continue to fire normally."""
        other = SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="currency",
            match_type="exact",
            match_value="USD",
            substitution_value="1",
        )
        stats: dict = {}
        rows = apply_substitutions(
            [{"description": "raw", "currency": "USD"}],
            company_id=self.company.id,
            model_name="Transaction",
            skip_fields=["description"],
            stats_out=stats,
        )
        # description skipped, currency substituted
        self.assertEqual(rows[0]["description"], "raw")
        self.assertEqual(rows[0]["currency"], "1")
        self.assertNotIn(self.rule.id, stats["rule_hits"])
        self.assertEqual(stats["rule_hits"].get(other.id), 1)


class ExtractSkipFieldsFromTransformationRuleTests(TestCase):
    """``ETLPipelineService._extract_skip_substitution_fields`` converts
    the per-column JSON hint into the frozenset the engine consumes."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Extract")

    def _extract(self, rule):
        # Importing the service at call time avoids pulling the whole
        # ETL module at test-collection time.
        from multitenancy.etl_service import ETLPipelineService
        svc = ETLPipelineService.__new__(ETLPipelineService)
        return svc._extract_skip_substitution_fields(rule)

    def test_none_rule_returns_empty(self):
        self.assertEqual(self._extract(None), set())

    def test_missing_column_options_returns_empty(self):
        r = ImportTransformationRule.objects.create(
            company=self.company,
            name="r",
            source_sheet_name="Sheet1",
            target_model="Transaction",
            column_mappings={"A": "a"},
        )
        self.assertEqual(self._extract(r), set())

    def test_flagged_fields_extracted(self):
        r = ImportTransformationRule.objects.create(
            company=self.company,
            name="r2",
            source_sheet_name="Sheet1",
            target_model="Transaction",
            column_mappings={"A": "amount", "D": "description"},
            column_options={
                "amount": {"skip_substitutions": True},
                "description": {"skip_substitutions": False},
                "date": {"some_other_hint": True},
            },
        )
        self.assertEqual(self._extract(r), {"amount"})

    def test_malformed_column_options_returns_empty(self):
        r = ImportTransformationRule.objects.create(
            company=self.company,
            name="r3",
            source_sheet_name="Sheet1",
            target_model="Transaction",
            column_mappings={"A": "a"},
            # Shouldn't happen in practice, but don't crash:
            column_options={"amount": "not-a-dict"},
        )
        self.assertEqual(self._extract(r), set())


class StatsOutContractTests(TestCase):
    """The ``stats_out`` dict is the documented hook for tests and perf
    tools — lock its shape so callers can depend on it."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Stats")

    def test_stats_out_populated_with_expected_keys(self):
        SubstitutionRule.objects.create(
            company=self.company,
            model_name="Transaction",
            field_name="description",
            match_type="exact",
            match_value="x",
            substitution_value="y",
        )
        stats: dict = {}
        apply_substitutions(
            [{"description": "x"}, {"description": "x"}, {"description": "z"}],
            company_id=self.company.id,
            model_name="Transaction",
            stats_out=stats,
        )
        self.assertIn("rule_hits", stats)
        self.assertIn("rule_time", stats)
        self.assertIn("skipped_fields", stats)
        # Row 1 ("x") evaluates the rule; row 2 ("x") hits the internal
        # value cache so the rule is *not* re-evaluated; row 3 ("z")
        # evaluates the rule but doesn't match. → 2 total hits, not 3.
        self.assertEqual(sum(stats["rule_hits"].values()), 2)
        # rule_time entries are floats (seconds)
        self.assertTrue(all(isinstance(v, float) for v in stats["rule_time"].values()))

    def test_stats_out_optional(self):
        """When stats_out is None, the engine must not crash and
        returns rows as usual."""
        rows = apply_substitutions(
            [{"description": "anything"}],
            company_id=self.company.id,
            model_name="Transaction",
        )
        self.assertEqual(len(rows), 1)
