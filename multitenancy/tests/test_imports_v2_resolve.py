"""Phase 4A — resolve endpoint + action handlers + staged-rule
materialisation on commit.

Covered:

  * Handler-level unit tests for pick_row / skip_group / ignore_row /
    abort — including the guardrails (wrong issue type, missing
    params, action not in proposed_actions).
  * Service-level ``resolve_session`` tests: happy path, partial
    resolution leaves session awaiting, abort flips to error, terminal
    sessions are rejected, unknown issue_id → ResolutionError, resolve
    re-detects issues so stale items disappear once rows are removed.
  * View tests: POST /resolve/<pk>/ validation + 404 on cross-tenant +
    409 on terminal + 200 happy path.
  * Commit tests: staged_substitution_rules materialises into real
    SubstitutionRule rows (source=import_session + source_session FK)
    and the commit response surfaces the created pks.
"""
from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from multitenancy.imports_v2 import resolve_handlers, services
from multitenancy.imports_v2.resolve_handlers import ResolutionError
from multitenancy.models import Company, ImportSession, SubstitutionRule

User = get_user_model()


# ---- fixtures ------------------------------------------------------------


def _make_conflict_issue(
    issue_id: str = "iss-1",
    sheet: str = "Transaction",
    erp_id: str = "OMIE-1",
    row_ids=("R1", "R2"),
):
    return {
        "issue_id": issue_id,
        "type": "erp_id_conflict",
        "severity": "error",
        "location": {"sheet": sheet, "erp_id": erp_id, "row_ids": list(row_ids)},
        "context": {"fields": {"date": ["2026-01-01", "2026-01-02"]}},
        "proposed_actions": ["pick_row", "skip_group", "abort"],
        "message": "conflict",
    }


def _make_template_session(
    company,
    *,
    status=ImportSession.STATUS_AWAITING_RESOLVE,
    rows=None,
    issues=None,
    staged=None,
):
    rows = rows if rows is not None else [
        {"__row_id": "R1", "__erp_id": "OMIE-1", "date": "2026-01-01",
         "amount": "100", "description": "x"},
        {"__row_id": "R2", "__erp_id": "OMIE-1", "date": "2026-01-02",
         "amount": "100", "description": "x"},
    ]
    return ImportSession.objects.create(
        company_id=company.id,
        mode=ImportSession.MODE_TEMPLATE,
        status=status,
        file_name="import.xlsx",
        file_bytes=b"<pretend xlsx>",
        parsed_payload={"sheets": {"Transaction": rows}},
        open_issues=issues if issues is not None else [_make_conflict_issue()],
        staged_substitution_rules=staged or [],
    )


# ---- handler unit tests --------------------------------------------------


class PickRowHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Pick")

    def test_pick_row_drops_other_rows_in_group(self):
        session = _make_template_session(self.company)
        issue = session.open_issues[0]
        result = resolve_handlers.handle_pick_row(
            session, issue, {"row_id": "R1"},
        )
        rows = session.parsed_payload["sheets"]["Transaction"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["__row_id"], "R1")
        self.assertEqual(result["kept_row_id"], "R1")
        self.assertEqual(result["dropped_row_ids"], ["R2"])
        self.assertEqual((result["rows_before"], result["rows_after"]), (2, 1))

    def test_pick_row_missing_params_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_pick_row(session, session.open_issues[0], {})

    def test_pick_row_id_not_in_group_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_pick_row(
                session, session.open_issues[0], {"row_id": "R99"},
            )

    def test_pick_row_wrong_issue_type_raises(self):
        session = _make_template_session(self.company)
        wrong = {**session.open_issues[0], "type": "bad_date_format"}
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_pick_row(session, wrong, {"row_id": "R1"})


class SkipGroupHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Skip")

    def test_skip_group_drops_every_row_of_group(self):
        session = _make_template_session(self.company, rows=[
            {"__row_id": "R1", "__erp_id": "OMIE-1", "amount": "100"},
            {"__row_id": "R2", "__erp_id": "OMIE-1", "amount": "100"},
            {"__row_id": "R3", "__erp_id": "OMIE-2", "amount": "50"},
        ])
        issue = _make_conflict_issue(row_ids=("R1", "R2"))
        result = resolve_handlers.handle_skip_group(session, issue, {})
        rows = session.parsed_payload["sheets"]["Transaction"]
        self.assertEqual([r["__row_id"] for r in rows], ["R3"])
        self.assertEqual(result["rows_before"], 3)
        self.assertEqual(result["rows_after"], 1)


class IgnoreRowHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Ignore")

    def test_ignore_row_drops_target(self):
        session = _make_template_session(self.company, rows=[
            {"__row_id": "R1", "amount": "100"},
            {"__row_id": "R2", "amount": "200"},
        ])
        issue = {
            "issue_id": "iss-99",
            "type": "negative_amount",
            "severity": "error",
            "location": {"sheet": "Transaction", "row_id": "R1"},
            "context": {},
            "proposed_actions": ["ignore_row"],
        }
        resolve_handlers.handle_ignore_row(session, issue, {"row_id": "R1"})
        rows = session.parsed_payload["sheets"]["Transaction"]
        self.assertEqual([r["__row_id"] for r in rows], ["R2"])

    def test_ignore_row_requires_location_sheet(self):
        session = _make_template_session(self.company)
        bad = {"issue_id": "x", "type": "negative_amount", "location": {}}
        with self.assertRaises(ResolutionError):
            resolve_handlers.handle_ignore_row(session, bad, {"row_id": "R1"})


class AbortHandlerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Abort")

    def test_abort_returns_abort_true(self):
        session = _make_template_session(self.company)
        result = resolve_handlers.handle_abort(
            session, session.open_issues[0], {"reason": "operator_cancel"},
        )
        self.assertTrue(result["abort"])
        self.assertEqual(result["reason"], "operator_cancel")


class ApplyResolutionDispatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Dispatch")

    def test_unknown_action_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            resolve_handlers.apply_resolution(
                session, session.open_issues[0], "nope", {},
            )

    def test_action_not_in_proposed_actions_raises(self):
        session = _make_template_session(self.company)
        # The conflict issue's proposed_actions doesn't include ignore_row.
        with self.assertRaises(ResolutionError):
            resolve_handlers.apply_resolution(
                session, session.open_issues[0], "ignore_row", {"row_id": "R1"},
            )


# ---- service-layer resolve_session tests ---------------------------------


class ResolveSessionServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Resolve")

    def test_pick_row_moves_session_to_ready(self):
        session = _make_template_session(self.company)
        resolved = services.resolve_session(session, [{
            "issue_id": "iss-1",
            "action": "pick_row",
            "params": {"row_id": "R1"},
        }])
        self.assertEqual(resolved.status, ImportSession.STATUS_READY)
        self.assertEqual(resolved.open_issues, [])
        self.assertEqual(len(resolved.resolutions), 1)
        record = resolved.resolutions[0]
        self.assertEqual(record["action"], "pick_row")
        self.assertEqual(record["result"]["kept_row_id"], "R1")

    def test_abort_moves_session_to_error(self):
        session = _make_template_session(self.company)
        resolved = services.resolve_session(session, [{
            "issue_id": "iss-1",
            "action": "abort",
            "params": {"reason": "user_cancel"},
        }])
        self.assertEqual(resolved.status, ImportSession.STATUS_ERROR)
        self.assertEqual(resolved.result["abort"]["reason"], "user_cancel")

    def test_partial_resolution_keeps_session_awaiting(self):
        """Resolving only one of two conflicts leaves the session in
        awaiting_resolve — the remaining conflict is re-detected."""
        rows = [
            {"__row_id": "R1", "__erp_id": "A", "date": "2026-01-01", "amount": "1"},
            {"__row_id": "R2", "__erp_id": "A", "date": "2026-01-02", "amount": "1"},
            {"__row_id": "R3", "__erp_id": "B", "date": "2026-02-01", "amount": "2"},
            {"__row_id": "R4", "__erp_id": "B", "date": "2026-02-02", "amount": "2"},
        ]
        issue_a = _make_conflict_issue("iss-a", erp_id="A", row_ids=("R1", "R2"))
        issue_b = _make_conflict_issue("iss-b", erp_id="B", row_ids=("R3", "R4"))
        session = _make_template_session(
            self.company, rows=rows, issues=[issue_a, issue_b],
        )
        resolved = services.resolve_session(session, [{
            "issue_id": "iss-a",
            "action": "pick_row",
            "params": {"row_id": "R1"},
        }])
        self.assertEqual(resolved.status, ImportSession.STATUS_AWAITING_RESOLVE)
        # Conflict A is gone; conflict B is still in open_issues.
        open_erp_ids = {i["location"]["erp_id"] for i in resolved.open_issues}
        self.assertEqual(open_erp_ids, {"B"})

    def test_terminal_session_raises(self):
        session = _make_template_session(
            self.company, status=ImportSession.STATUS_COMMITTED,
        )
        with self.assertRaises(services.ResolveNotApplicable):
            services.resolve_session(session, [])

    def test_committing_session_raises(self):
        session = _make_template_session(
            self.company, status=ImportSession.STATUS_COMMITTING,
        )
        with self.assertRaises(services.ResolveNotApplicable):
            services.resolve_session(session, [])

    def test_unknown_issue_id_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            services.resolve_session(session, [{
                "issue_id": "iss-nope",
                "action": "pick_row",
                "params": {"row_id": "R1"},
            }])

    def test_missing_action_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            services.resolve_session(session, [{"issue_id": "iss-1"}])

    def test_non_dict_resolution_raises(self):
        session = _make_template_session(self.company)
        with self.assertRaises(ResolutionError):
            services.resolve_session(session, ["not a dict"])


# ---- view (HTTP) tests ---------------------------------------------------


def _url_resolve_template(tenant_id, pk):
    return f"/{tenant_id}/api/core/imports/v2/resolve/{pk}/"


def _url_session(tenant_id, pk):
    return f"/{tenant_id}/api/core/imports/v2/sessions/{pk}/"


def _url_commit(tenant_id, pk):
    return f"/{tenant_id}/api/core/imports/v2/commit/{pk}/"


@override_settings(AUTH_OFF=True)
class ResolveViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.co1 = Company.objects.create(name="Acme View")
        cls.co2 = Company.objects.create(name="Globex View")
        cls.user = User.objects.create_user(username="op", password="x")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_missing_resolutions_returns_400(self):
        session = _make_template_session(self.co1)
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk), {}, format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_resolutions_not_list_returns_400(self):
        session = _make_template_session(self.co1)
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk),
            {"resolutions": "nope"}, format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_happy_path_pick_row_returns_200_and_ready(self):
        session = _make_template_session(self.co1)
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk),
            {"resolutions": [{
                "issue_id": "iss-1",
                "action": "pick_row",
                "params": {"row_id": "R1"},
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_READY)
        self.assertTrue(body["is_committable"])

    def test_terminal_session_returns_409(self):
        session = _make_template_session(
            self.co1, status=ImportSession.STATUS_COMMITTED,
        )
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk),
            {"resolutions": []}, format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_cross_tenant_returns_404(self):
        session = _make_template_session(self.co2)
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk),
            {"resolutions": []}, format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_unknown_action_returns_400(self):
        session = _make_template_session(self.co1)
        resp = self.client.post(
            _url_resolve_template(self.co1.id, session.pk),
            {"resolutions": [{
                "issue_id": "iss-1",
                "action": "nope",
                "params": {},
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


# ---- commit → staged-rule materialisation --------------------------------


@override_settings(AUTH_OFF=True)
class CommitMaterialisesStagedRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Stage")
        cls.user = User.objects.create_user(username="op", password="x")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _ready_session_with_staged_rules(self, staged):
        return ImportSession.objects.create(
            company_id=self.company.id,
            created_by=self.user,
            mode=ImportSession.MODE_TEMPLATE,
            status=ImportSession.STATUS_READY,
            file_name="ok.xlsx",
            file_bytes=b"<pretend xlsx>",
            parsed_payload={"sheets": {"Transaction": [{"amount": "100"}]}},
            open_issues=[],
            staged_substitution_rules=staged,
        )

    def test_commit_creates_substitutionrule_rows_with_source_and_fk(self):
        session = self._ready_session_with_staged_rules([
            {
                "model_name": "Entity",
                "field_name": "id",
                "match_type": "caseless",
                "match_value": "Fornecedor X",
                "substitution_value": "42",
                "title": "Via operator resolve",
            },
        ])
        fake_result = {"imports": [{"model": "Transaction", "created": 1}]}
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value=fake_result,
        ):
            resp = self.client.post(
                _url_commit(self.company.id, session.pk), {}, format="json",
            )
        # Phase 6.z-a: commit is async. In eager mode the worker has
        # already run so the 202 body already carries the committed
        # session — including the created_pks we want to inspect.
        self.assertEqual(resp.status_code, 202, resp.content)
        created_pks = resp.json()["result"]["substitution_rules_created"]
        self.assertEqual(len(created_pks), 1)
        rule = SubstitutionRule.objects.get(pk=created_pks[0])
        self.assertEqual(rule.source, SubstitutionRule.SOURCE_IMPORT_SESSION)
        self.assertEqual(rule.source_session_id, session.pk)
        self.assertEqual(rule.model_name, "Entity")
        self.assertEqual(rule.field_name, "id")
        self.assertEqual(rule.match_type, "caseless")
        self.assertEqual(rule.match_value, "Fornecedor X")
        self.assertEqual(rule.substitution_value, "42")
        self.assertEqual(rule.title, "Via operator resolve")

    def test_malformed_staged_entry_rolls_back_commit(self):
        session = self._ready_session_with_staged_rules([
            "not a dict — malformed",
        ])
        before_count = SubstitutionRule.objects.count()
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value={"imports": []},
        ):
            resp = self.client.post(
                _url_commit(self.company.id, session.pk), {}, format="json",
            )
        # Phase 6.z-a: commit failures no longer return 500 — the view
        # returns 202 and the worker writes the ``error`` status on the
        # session. Frontend reads the final state via polling. In eager
        # mode the 202 body already reflects the terminal error state.
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertEqual(resp.json()["status"], ImportSession.STATUS_ERROR)
        session.refresh_from_db()
        self.assertEqual(session.status, ImportSession.STATUS_ERROR)
        # Rollback: no rule was created.
        self.assertEqual(SubstitutionRule.objects.count(), before_count)

    def test_commit_with_no_staged_rules_still_reports_empty_list(self):
        session = self._ready_session_with_staged_rules([])
        fake_result = {"imports": []}
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value=fake_result,
        ):
            resp = self.client.post(
                _url_commit(self.company.id, session.pk), {}, format="json",
            )
        # Phase 6.z-a: async commit → 202. Eager-mode body already
        # carries the committed session.
        self.assertEqual(resp.status_code, 202, resp.content)
        self.assertEqual(
            resp.json()["result"]["substitution_rules_created"], [],
        )


# ---- end-to-end: analyze → resolve → commit ------------------------------


@override_settings(AUTH_OFF=True)
class AnalyzeResolveCommitFlowTests(TestCase):
    """End-to-end: upload a file with a conflict, resolve it via the
    endpoint, then commit — the whole dance.
    """

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme E2E")
        cls.user = User.objects.create_user(username="op", password="x")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_analyze_conflict_pick_row_commit(self):
        import io
        import pandas as pd

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            # __row_id values let pick_row target one of the conflicting
            # rows by id — without them, the grouping helper surfaces
            # ``[None, None]`` which is ambiguous (and rejected by the
            # handler as a missing row_id).
            pd.DataFrame([
                {"__row_id": "R1", "__erp_id": "OMIE-1", "date": "2026-01-01",
                 "description": "x", "amount": "100"},
                {"__row_id": "R2", "__erp_id": "OMIE-1", "date": "2026-01-02",
                 "description": "x", "amount": "100"},
            ]).to_excel(xw, sheet_name="Transaction", index=False)
        buf.seek(0)
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile(
            "import.xlsx", buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # 1) analyze — session lands in awaiting_resolve with one conflict
        resp = self.client.post(
            f"/{self.company.id}/api/core/imports/v2/analyze/",
            {"file": file}, format="multipart",
        )
        # Phase 6.z-a: analyze is async, view returns 202 Accepted.
        self.assertEqual(resp.status_code, 202, resp.content)
        analyze_body = resp.json()
        self.assertEqual(
            analyze_body["status"], ImportSession.STATUS_AWAITING_RESOLVE,
        )
        issue_id = analyze_body["open_issues"][0]["issue_id"]
        row_ids = analyze_body["open_issues"][0]["location"]["row_ids"]
        session_id = analyze_body["id"]

        # 2) resolve with pick_row — session advances to ready
        resp = self.client.post(
            f"/{self.company.id}/api/core/imports/v2/resolve/{session_id}/",
            {"resolutions": [{
                "issue_id": issue_id,
                "action": "pick_row",
                "params": {"row_id": row_ids[0]},
            }]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json()["status"], ImportSession.STATUS_READY,
        )

        # 3) commit — with execute_import_job mocked, session transitions
        #    to committed and no rules get created (none were staged).
        fake_result = {"imports": [{"model": "Transaction", "created": 1}]}
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value=fake_result,
        ):
            resp = self.client.post(
                f"/{self.company.id}/api/core/imports/v2/commit/{session_id}/",
                {}, format="json",
            )
        # Phase 6.z-a: async commit → 202. Eager-mode body carries the
        # committed session.
        self.assertEqual(resp.status_code, 202, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_COMMITTED)
        self.assertEqual(body["result"]["substitution_rules_created"], [])
