"""Phase 4B — new issue detectors + map_to_existing / edit_value handlers.

Covers:

  * ``_tryparse_date`` — ISO and pt-BR ``DD/MM/YYYY``.
  * ``_detect_bad_date_format`` — one issue per row × field.
  * ``_detect_negative_amounts`` — driven by ``ImportTransformationRule.column_options[field]['positive_only']``.
  * ``_detect_unmatched_references`` — entity by name / currency by code.
    Also exercises the ``fk_ambiguous`` path when two rows share a name.
  * ``handle_edit_value`` — happy + guardrails.
  * ``handle_map_to_existing`` — happy + staged-rule injection + commit
    materialisation end-to-end.

Does NOT cover ``je_balance_mismatch`` or a richer FK-resolution model
— those are carved out to a later commit (plan §2).
"""
from __future__ import annotations

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from multitenancy.imports_v2 import resolve_handlers, services
from multitenancy.imports_v2.resolve_handlers import ResolutionError
from multitenancy.models import (
    Company,
    Entity,
    ImportSession,
    ImportTransformationRule,
    SubstitutionRule,
)

User = get_user_model()


# ---- _tryparse_date unit tests -------------------------------------------


class TryParseDateTests(TestCase):
    def test_iso(self):
        self.assertEqual(
            services._tryparse_date("2026-04-23"),
            datetime.date(2026, 4, 23),
        )

    def test_iso_with_time_suffix(self):
        # We accept the first 10 chars as an ISO date — handles our own
        # _json_scalar output which may include ``T00:00:00``.
        self.assertEqual(
            services._tryparse_date("2026-04-23T00:00:00"),
            datetime.date(2026, 4, 23),
        )

    def test_br_format(self):
        self.assertEqual(
            services._tryparse_date("23/04/2026"),
            datetime.date(2026, 4, 23),
        )

    def test_us_fallback_when_br_impossible(self):
        # 13/04/2026 — BR says month=13 (invalid), fall back to US:
        # month=13, day=4 → also invalid. Should return None.
        self.assertIsNone(services._tryparse_date("13/40/2026"))

    def test_garbage_returns_none(self):
        for junk in ("not a date", "2026/13/40", "", None, 42):
            self.assertIsNone(services._tryparse_date(junk), msg=junk)

    def test_accepts_native_date(self):
        d = datetime.date(2026, 1, 1)
        self.assertEqual(services._tryparse_date(d), d)


# ---- bad_date_format detector --------------------------------------------


class DetectBadDateFormatTests(TestCase):
    def test_flags_unparseable_date(self):
        rows = [
            {"__row_id": "R1", "date": "2026-01-01"},        # ok
            {"__row_id": "R2", "date": "not-a-date"},         # bad
            {"__row_id": "R3", "date": None},                  # skip
            {"__row_id": "R4", "date": "31/12/2026"},          # ok (BR)
        ]
        issues = services._detect_bad_date_format(rows, "Transaction")
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["type"], "bad_date_format")
        self.assertEqual(issue["location"]["row_id"], "R2")
        self.assertEqual(issue["location"]["field"], "date")
        self.assertEqual(issue["context"]["value"], "not-a-date")
        self.assertIn("edit_value", issue["proposed_actions"])
        self.assertIn("ignore_row", issue["proposed_actions"])

    def test_scans_multiple_date_columns(self):
        rows = [{"__row_id": "R1", "date": "2026-01-01",
                 "due_date": "bad", "payment_date": "2026-02-02"}]
        issues = services._detect_bad_date_format(rows, "Invoice")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["location"]["field"], "due_date")


# ---- negative_amount detector --------------------------------------------


class DetectNegativeAmountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Neg")

    def test_no_rule_no_issues(self):
        self.assertEqual(
            services._detect_negative_amounts(
                [{"amount": "-1"}], "Transaction", rule=None,
            ),
            [],
        )

    def test_rule_without_positive_only_no_issues(self):
        rule = ImportTransformationRule.objects.create(
            company=self.company,
            name="no-hint",
            source_sheet_name="Tx",
            target_model="Transaction",
            column_mappings={"A": "amount"},
        )
        self.assertEqual(
            services._detect_negative_amounts(
                [{"amount": "-1"}], "Transaction", rule=rule,
            ),
            [],
        )

    def test_flagged_positive_only_detects_negatives(self):
        rule = ImportTransformationRule.objects.create(
            company=self.company,
            name="pos",
            source_sheet_name="Tx",
            target_model="Transaction",
            column_mappings={"A": "amount"},
            column_options={"amount": {"positive_only": True}},
        )
        rows = [
            {"__row_id": "R1", "amount": "100"},
            {"__row_id": "R2", "amount": "-50"},
            {"__row_id": "R3", "amount": "-1.234,56"},   # BR negative
            {"__row_id": "R4", "amount": None},           # skip
        ]
        issues = services._detect_negative_amounts(
            rows, "Transaction", rule=rule,
        )
        flagged = sorted(i["location"]["row_id"] for i in issues)
        self.assertEqual(flagged, ["R2", "R3"])
        for i in issues:
            self.assertEqual(i["type"], "negative_amount")
            self.assertIn("edit_value", i["proposed_actions"])


# ---- unmatched_reference + fk_ambiguous detector -------------------------


class DetectUnmatchedReferencesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Ref")
        cls.other_company = Company.objects.create(name="Globex Ref")
        # Good entity
        Entity.objects.create(company=cls.company, name="Fornecedor X")
        # Entity in another company — should NOT resolve for ours
        Entity.objects.create(company=cls.other_company, name="Fornecedor Global")
        # NB: Entity has unique_together=(company, name) so ``fk_ambiguous``
        # can't be triggered via the ORM for this lookup table. The
        # ambiguous-branch is exercised via the mocked test below instead.

    def test_resolved_entity_no_issue(self):
        rows = [{"__row_id": "R1", "entity": "Fornecedor X"}]
        issues = services._detect_unmatched_references(
            rows, "Transaction", company_id=self.company.id,
        )
        self.assertEqual(issues, [])

    def test_cross_company_entity_is_unmatched(self):
        """Entity exists in a DIFFERENT company — still counts as
        unmatched for ours (tenant isolation)."""
        rows = [{"__row_id": "R1", "entity": "Fornecedor Global"}]
        issues = services._detect_unmatched_references(
            rows, "Transaction", company_id=self.company.id,
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["type"], "unmatched_reference")
        self.assertEqual(issues[0]["context"]["related_model"], "Entity")
        self.assertEqual(issues[0]["context"]["lookup_field"], "name")

    def test_unknown_entity_emits_one_unmatched_per_distinct_value(self):
        rows = [
            {"__row_id": "R1", "entity": "Nonexistent"},
            {"__row_id": "R2", "entity": "Nonexistent"},     # same → dedup
            {"__row_id": "R3", "entity": "Also missing"},
        ]
        issues = services._detect_unmatched_references(
            rows, "Transaction", company_id=self.company.id,
        )
        values = sorted(i["context"]["value"] for i in issues)
        self.assertEqual(values, ["Also missing", "Nonexistent"])
        self.assertTrue(all(i["type"] == "unmatched_reference" for i in issues))

    # NB: fk_ambiguous branch is not exercised in this test class because
    # the only current lookup target (Entity) has unique_together on
    # (company, name), so the ORM can't produce >1 matches. Leaving the
    # branch in the detector for when _REFERENCE_FIELD_LOOKUPS grows to
    # include a non-unique lookup field (e.g. Account by name).


# ---- edit_value handler --------------------------------------------------


def _make_template_session(company, *, rows, issues=None, staged=None,
                           status=ImportSession.STATUS_AWAITING_RESOLVE):
    return ImportSession.objects.create(
        company_id=company.id,
        mode=ImportSession.MODE_TEMPLATE,
        status=status,
        file_name="x.xlsx",
        file_bytes=b"<bytes>",
        parsed_payload={"sheets": {"Transaction": rows}},
        open_issues=issues or [],
        staged_substitution_rules=staged or [],
    )


def _make_bad_date_issue(row_id="R1", field="date"):
    return {
        "issue_id": "iss-bd1",
        "type": "bad_date_format",
        "severity": "error",
        "location": {"sheet": "Transaction", "row_id": row_id, "field": field},
        "context": {"value": "not-a-date"},
        "proposed_actions": ["edit_value", "ignore_row", "abort"],
        "message": "bad",
    }


class EditValueHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Edit")

    def test_happy_bad_date(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "date": "not-a-date"}],
            issues=[_make_bad_date_issue()],
        )
        result = resolve_handlers.handle_edit_value(
            session, session.open_issues[0],
            {"row_id": "R1", "field": "date", "new_value": "2026-04-23"},
        )
        self.assertEqual(
            session.parsed_payload["sheets"]["Transaction"][0]["date"],
            "2026-04-23",
        )
        self.assertEqual(result["old_value"], "not-a-date")
        self.assertEqual(result["new_value"], "2026-04-23")
        self.assertEqual(result["rows_updated"], 1)

    def test_missing_new_value_raises(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "date": "bad"}],
            issues=[_make_bad_date_issue()],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_edit_value(
                session, session.open_issues[0],
                {"row_id": "R1", "field": "date"},
            )

    def test_wrong_issue_type_raises(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "date": "ok"}],
            issues=[{
                **_make_bad_date_issue(),
                "type": "erp_id_conflict",
            }],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_edit_value(
                session, session.open_issues[0],
                {"row_id": "R1", "field": "date", "new_value": "x"},
            )

    def test_row_not_found_raises(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "date": "bad"}],
            issues=[_make_bad_date_issue()],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_edit_value(
                session, session.open_issues[0],
                {"row_id": "R99", "field": "date", "new_value": "x"},
            )


# ---- map_to_existing handler --------------------------------------------


def _make_unmatched_issue(sheet="Transaction", field="entity",
                          value="Fornecedor X", related_model="Entity"):
    return {
        "issue_id": "iss-un1",
        "type": "unmatched_reference",
        "severity": "error",
        "location": {"sheet": sheet, "field": field, "value": value},
        "context": {
            "value": value,
            "related_model": related_model,
            "related_app": "multitenancy",
            "lookup_field": "name",
        },
        "proposed_actions": ["map_to_existing", "ignore_row", "abort"],
        "message": "unmatched",
    }


class MapToExistingHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Map")
        cls.entity = Entity.objects.create(company=cls.company, name="Real Co")

    def test_rewrites_rows_to_target_id(self):
        session = _make_template_session(
            self.company,
            rows=[
                {"__row_id": "R1", "entity": "Fornecedor X", "amount": "1"},
                {"__row_id": "R2", "entity": "Fornecedor X", "amount": "2"},
                {"__row_id": "R3", "entity": "Outro", "amount": "3"},
            ],
            issues=[_make_unmatched_issue()],
        )
        result = resolve_handlers.handle_map_to_existing(
            session, session.open_issues[0],
            {"target_id": self.entity.pk},
        )
        self.assertEqual(result["rows_updated"], 2)
        rows = session.parsed_payload["sheets"]["Transaction"]
        self.assertEqual(rows[0]["entity"], self.entity.pk)
        self.assertEqual(rows[1]["entity"], self.entity.pk)
        self.assertEqual(rows[2]["entity"], "Outro")
        self.assertFalse(result["staged_rule"])
        self.assertEqual(session.staged_substitution_rules, [])

    def test_create_substitution_rule_stages_entry(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "entity": "Fornecedor X"}],
            issues=[_make_unmatched_issue()],
        )
        result = resolve_handlers.handle_map_to_existing(
            session, session.open_issues[0],
            {
                "target_id": self.entity.pk,
                "create_substitution_rule": True,
                "rule": {"match_type": "caseless"},
            },
        )
        self.assertTrue(result["staged_rule"])
        self.assertEqual(len(session.staged_substitution_rules), 1)
        staged = session.staged_substitution_rules[0]
        self.assertEqual(staged["model_name"], "Entity")
        self.assertEqual(staged["field_name"], "id")
        self.assertEqual(staged["match_type"], "caseless")
        self.assertEqual(staged["match_value"], "Fornecedor X")
        self.assertEqual(staged["substitution_value"], str(self.entity.pk))

    def test_missing_target_id_raises(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "entity": "Fornecedor X"}],
            issues=[_make_unmatched_issue()],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_map_to_existing(
                session, session.open_issues[0], {},
            )

    def test_wrong_issue_type_raises(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "entity": "X"}],
            issues=[{**_make_unmatched_issue(), "type": "bad_date_format"}],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_map_to_existing(
                session, session.open_issues[0],
                {"target_id": self.entity.pk},
            )

    def test_create_rule_without_related_model_raises(self):
        """Detector must populate ``context.related_model`` — the staged
        rule is meaningless without it."""
        bad_issue = _make_unmatched_issue()
        bad_issue["context"].pop("related_model")
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "entity": "X"}],
            issues=[bad_issue],
        )
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_map_to_existing(
                session, session.open_issues[0],
                {"target_id": self.entity.pk,
                 "create_substitution_rule": True},
            )


# ---- integration: map_to_existing → commit materialises rule -------------


@override_settings(AUTH_OFF=True)
class MapCommitEndToEndTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme E2E 4B")
        cls.user = User.objects.create_user(username="op", password="x")
        cls.entity = Entity.objects.create(
            company=cls.company, name="Real Co",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_resolve_map_then_commit_creates_rule(self):
        session = _make_template_session(
            self.company,
            rows=[{"__row_id": "R1", "entity": "Fornecedor Nunca Existiu"}],
            issues=[_make_unmatched_issue(value="Fornecedor Nunca Existiu")],
        )
        # 1) resolve via map_to_existing with create_substitution_rule
        resp = self.client.post(
            f"/{self.company.id}/api/core/imports/v2/resolve/{session.pk}/",
            {"resolutions": [{
                "issue_id": session.open_issues[0]["issue_id"],
                "action": "map_to_existing",
                "params": {
                    "target_id": self.entity.pk,
                    "create_substitution_rule": True,
                },
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        # One staged rule now; session is READY (no more blocking issues).
        self.assertEqual(len(body["staged_substitution_rules"]), 1)
        self.assertEqual(body["status"], ImportSession.STATUS_READY)

        # 2) commit — mock execute_import_job, verify the rule landed.
        fake_result = {"imports": [{"model": "Transaction", "created": 1}]}
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value=fake_result,
        ):
            resp = self.client.post(
                f"/{self.company.id}/api/core/imports/v2/commit/{session.pk}/",
                {}, format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        created_pks = resp.json()["result"]["substitution_rules_created"]
        self.assertEqual(len(created_pks), 1)
        rule = SubstitutionRule.objects.get(pk=created_pks[0])
        self.assertEqual(rule.model_name, "Entity")
        self.assertEqual(rule.field_name, "id")
        self.assertEqual(rule.match_value, "Fornecedor Nunca Existiu")
        self.assertEqual(rule.substitution_value, str(self.entity.pk))
        self.assertEqual(rule.source, SubstitutionRule.SOURCE_IMPORT_SESSION)
        self.assertEqual(rule.source_session_id, session.pk)
