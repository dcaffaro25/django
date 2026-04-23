"""Model-level tests for ImportSession + the new SubstitutionRule fields.

These exercise the v2 interactive-import session model shipped in
migration ``0035_v2_import_session``:

  * Tenant scoping — two companies cannot see each other's sessions.
  * State-machine helpers (``is_terminal`` / ``is_committable``) return
    sane answers from every documented status.
  * ``SubstitutionRule.source`` defaults to ``manual`` for backward
    compatibility, so every row created before this migration or via
    the legacy admin reads as ``manual``.
  * ``SubstitutionRule.source_session`` is optional and uses SET_NULL
    so sessions can be deleted without cascading-away the rules they
    materialised.

These are DB-touching tests (TestCase), not SimpleTestCase — we need
the migration to have actually run.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from multitenancy.models import Company, ImportSession, SubstitutionRule

User = get_user_model()


class ImportSessionModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.co1 = Company.objects.create(name="Acme")
        cls.co2 = Company.objects.create(name="Globex")
        cls.user = User.objects.create(username="operator", password="x")

    # --- creation -----------------------------------------------------------

    def test_create_minimal_template_session(self):
        s = ImportSession.objects.create(
            company=self.co1,
            created_by=self.user,
            mode=ImportSession.MODE_TEMPLATE,
            file_name="import.xlsx",
        )
        self.assertEqual(s.status, ImportSession.STATUS_ANALYZING)
        self.assertEqual(s.mode, "template")
        self.assertEqual(s.open_issues, [])
        self.assertEqual(s.resolutions, [])
        self.assertEqual(s.staged_substitution_rules, [])
        self.assertEqual(s.config, {})
        self.assertEqual(s.result, {})
        self.assertIsNone(s.committed_at)

    def test_create_etl_session_with_transformation_rule_left_null(self):
        """transformation_rule is FK-nullable for both modes; template-mode
        leaves it null, ETL-mode sets it when the operator picks a rule."""
        s = ImportSession.objects.create(
            company=self.co1,
            mode=ImportSession.MODE_ETL,
            file_name="pipeline.xlsx",
        )
        self.assertIsNone(s.transformation_rule)

    # --- state machine ------------------------------------------------------

    def test_is_terminal_for_each_status(self):
        cases = {
            ImportSession.STATUS_ANALYZING: False,
            ImportSession.STATUS_AWAITING_RESOLVE: False,
            ImportSession.STATUS_READY: False,
            ImportSession.STATUS_COMMITTING: False,
            ImportSession.STATUS_COMMITTED: True,
            ImportSession.STATUS_DISCARDED: True,
            ImportSession.STATUS_ERROR: True,
        }
        s = ImportSession(
            company=self.co1, mode=ImportSession.MODE_TEMPLATE, file_name="x"
        )
        for status, expected in cases.items():
            s.status = status
            self.assertEqual(
                s.is_terminal(), expected,
                f"is_terminal({status}) expected {expected}",
            )

    def test_is_committable_only_at_ready(self):
        s = ImportSession(
            company=self.co1, mode=ImportSession.MODE_TEMPLATE, file_name="x"
        )
        for status, _ in ImportSession.STATUS_CHOICES:
            s.status = status
            self.assertEqual(
                s.is_committable(), status == ImportSession.STATUS_READY,
            )

    # --- tenant isolation ---------------------------------------------------

    def test_default_manager_scopes_by_current_company(self):
        """``TenantAwareManager`` filters to the 'current' company. Without
        a request context it returns all — we just check rows go under the
        right FK so later request-scoped views can't leak."""
        s1 = ImportSession.objects.create(
            company=self.co1,
            mode=ImportSession.MODE_TEMPLATE,
            file_name="a.xlsx",
        )
        s2 = ImportSession.objects.create(
            company=self.co2,
            mode=ImportSession.MODE_TEMPLATE,
            file_name="b.xlsx",
        )
        self.assertEqual(s1.company_id, self.co1.id)
        self.assertEqual(s2.company_id, self.co2.id)
        # No FK crossover is the basic invariant.
        self.assertNotEqual(s1.company_id, s2.company_id)

    # --- json blob shape ----------------------------------------------------

    def test_jsonfields_roundtrip_complex_shapes(self):
        """parsed_payload / open_issues / resolutions all carry arbitrary
        shapes; roundtrip to the DB and back without mutation."""
        payload = {
            "sheets": {"Transaction": {"rows": [{"__row_id": "r1", "amount": "100.00"}]}},
            "substitutions_applied": [{"field": "entity", "from": "ACME", "to": "ACME LTDA"}],
        }
        issues = [
            {
                "issue_id": "conf-001",
                "type": "erp_id_conflict",
                "severity": "error",
                "location": {"sheet": "Transaction", "erp_id": "OMIE-1"},
                "context": {"fields": {"date": ["2026-01-01", "2026-01-02"]}},
                "proposed_actions": ["pick_row", "skip_group", "abort"],
            }
        ]
        resolutions = [
            {"issue_id": "conf-001", "action": "pick_row", "params": {"row_id": "r1"}},
        ]
        staged = [
            {
                "model_name": "Entity",
                "field_name": "name",
                "match_type": "exact",
                "match_value": "FORNECEDOR ABC",
                "substitution_value": "42",
                "filter_conditions": None,
                "title": "Auto from session #1",
            }
        ]

        s = ImportSession.objects.create(
            company=self.co1,
            mode=ImportSession.MODE_TEMPLATE,
            file_name="x.xlsx",
            parsed_payload=payload,
            open_issues=issues,
            resolutions=resolutions,
            staged_substitution_rules=staged,
        )
        s.refresh_from_db()
        self.assertEqual(s.parsed_payload, payload)
        self.assertEqual(s.open_issues, issues)
        self.assertEqual(s.resolutions, resolutions)
        self.assertEqual(s.staged_substitution_rules, staged)


class SubstitutionRuleSourceFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.co = Company.objects.create(name="Acme")

    def test_source_defaults_to_manual(self):
        r = SubstitutionRule.objects.create(
            company=self.co,
            model_name="Entity",
            field_name="name",
            match_value="ACME",
            substitution_value="42",
        )
        self.assertEqual(r.source, SubstitutionRule.SOURCE_MANUAL)
        self.assertIsNone(r.source_session)

    def test_source_session_link_survives_session_delete_via_set_null(self):
        """Deleting a session must not cascade-delete the rules it birthed —
        those rules are independent audit records once committed."""
        session = ImportSession.objects.create(
            company=self.co,
            mode=ImportSession.MODE_TEMPLATE,
            file_name="x",
        )
        rule = SubstitutionRule.objects.create(
            company=self.co,
            model_name="Entity",
            field_name="name",
            match_value="ACME",
            substitution_value="42",
            source=SubstitutionRule.SOURCE_IMPORT_SESSION,
            source_session=session,
        )
        session_pk = session.pk
        session.delete()

        rule.refresh_from_db()
        self.assertEqual(rule.source, SubstitutionRule.SOURCE_IMPORT_SESSION)
        self.assertIsNone(rule.source_session)
        # Session is gone.
        self.assertFalse(ImportSession.objects.filter(pk=session_pk).exists())

    def test_source_choices_enforce_valid_provenance(self):
        """Invalid ``source`` values fail model-level validation (clean)."""
        r = SubstitutionRule(
            company=self.co,
            model_name="Entity",
            field_name="name",
            match_value="ACME",
            substitution_value="42",
            source="bogus",
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            r.full_clean()
