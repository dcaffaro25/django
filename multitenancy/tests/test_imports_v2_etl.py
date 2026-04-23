"""Integration tests for the v2 ETL backend (Phase 3).

Covers:
  * ``/api/core/etl/v2/analyze/`` — rule resolution + mode=etl + session
    populated from (mocked) ``ETLPipelineService.execute()``.
  * ``missing_etl_parameter`` issue is raised when the rule declares an
    auto-JE column that doesn't appear in transformed rows.
  * ``substitutions_applied`` is carried through from the ETL service
    into the session's parsed_payload.
  * ``erp_id_conflict`` still fires in ETL mode when post-transform
    Transaction rows disagree on shared fields.
  * ``/api/core/etl/v2/sessions/<id>/`` and ``/commit/<id>/`` are
    reachable via the ETL URL namespace AND resolve to the same
    session-detail / commit views used by the template namespace.
  * Commit for an ETL-mode session re-runs ``ETLPipelineService`` with
    ``commit=True`` (mocked) — no FK fixture sprawl needed here.

All external I/O (``ETLPipelineService.execute`` + the pipeline's
lookup_cache / DB FK resolution) is mocked. Phase 4 tests will
exercise the real write when the resolve flow lands.
"""
from __future__ import annotations

import io
import json
from unittest import mock

import pandas as pd


def _json_dump(obj) -> str:
    return json.dumps(obj)
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from multitenancy.models import (
    Company,
    ImportSession,
    ImportTransformationRule,
)

User = get_user_model()


def _build_xlsx(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, rows in sheets.items():
            df = pd.DataFrame(rows or [{}])
            df.to_excel(xw, sheet_name=name, index=False)
    buf.seek(0)
    return buf.getvalue()


def _upload_file(content: bytes, name: str = "import.xlsx"):
    return SimpleUploadedFile(
        name, content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# URL helpers. ETL namespace mounts at ``/<tenant>/api/core/etl/v2/...``.
def _url_etl_analyze(tenant):
    return f"/{tenant}/api/core/etl/v2/analyze/"


def _url_etl_commit(tenant, pk):
    return f"/{tenant}/api/core/etl/v2/commit/{pk}/"


def _url_etl_session(tenant, pk):
    return f"/{tenant}/api/core/etl/v2/sessions/{pk}/"


@override_settings(AUTH_OFF=True)
class ETLv2AnalyzeEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Co")
        cls.user = User.objects.create_user(username="op", password="x")
        cls.rule = ImportTransformationRule.objects.create(
            company_id=cls.company.id,
            name="Test rule",
            source_sheet_name="Transaction",
            target_model="Transaction",
            column_mappings={"Data": "date", "Valor": "amount"},
        )
        # auto_create_journal_entries is not a field on the rule; it's
        # passed per-request to match legacy ETL semantics. Tests pass
        # it via request body below.
        cls.AUTO_JE_CONFIG = {
            "enabled": True,
            "bank_account_field": "bank_account_id",
            "opposing_account_field": "account_path",
        }

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_missing_rule_id_returns_400(self):
        resp = self.client.post(
            _url_etl_analyze(self.company.id),
            {"file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]}))},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("transformation_rule_id", resp.json().get("error", ""))

    def test_unknown_rule_id_marks_session_error(self):
        """Passing a rule_id that doesn't belong to this tenant creates a
        session in the ERROR state rather than 400 — keeps the error
        surface uniform with parse failures."""
        with mock.patch("multitenancy.imports_v2.services.ETLPipelineService") as svc:
            resp = self.client.post(
                _url_etl_analyze(self.company.id),
                {
                    "file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]})),
                    "transformation_rule_id": "99999",
                },
                format="multipart",
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_ERROR)
        self.assertIn("not found", body.get("result", {}).get("error", ""))
        # ETLPipelineService should NEVER have been called for a
        # non-existent rule.
        svc.assert_not_called()

    def test_happy_path_clean_file_transitions_to_ready(self):
        """Mock the ETL service to return a clean payload — session
        should land in READY, and parsed_payload should carry through
        the substitutions_applied + transformed_data we fed it."""
        etl_return = {
            "transformed_data": {
                "Transaction": {
                    "row_count": 1,
                    "rows": [{
                        "__erp_id": "OMIE-1",
                        "date": "2026-01-01",
                        "amount": "100.00",
                        "bank_account_id": 42,
                        "account_path": "Despesas > Aluguel",
                    }],
                    "sample_columns": [],
                },
            },
            "substitutions_applied": [
                {"field": "account_path", "from": "Aluguel", "to": "Despesas > Aluguel"},
            ],
            "python_errors": [],
            "database_errors": [],
            "substitution_errors": [],
            "warnings": [],
            "sheets_processed": ["Transaction"],
        }
        with mock.patch("multitenancy.imports_v2.services.ETLPipelineService") as svc_cls:
            svc_cls.return_value.execute.return_value = etl_return
            resp = self.client.post(
                _url_etl_analyze(self.company.id),
                {
                    "file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]})),
                    "transformation_rule_id": str(self.rule.pk),
                    "auto_create_journal_entries": _json_dump(self.AUTO_JE_CONFIG),
                },
                format="multipart",
            )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["mode"], "etl")
        self.assertEqual(body["status"], ImportSession.STATUS_READY)
        self.assertEqual(
            body["substitutions_applied"],
            [{"field": "account_path", "from": "Aluguel", "to": "Despesas > Aluguel"}],
        )
        self.assertEqual(body["open_issues"], [])

    def test_missing_etl_parameter_raises_issue(self):
        """Rule declares auto_create_journal_entries.bank_account_field
        = 'bank_account_id' but the transformed rows don't have that
        key → emits a missing_etl_parameter issue and blocks commit."""
        etl_return = {
            "transformed_data": {
                "Transaction": {
                    "row_count": 1,
                    "rows": [{
                        "__erp_id": "OMIE-1",
                        "date": "2026-01-01",
                        "amount": "100.00",
                        # bank_account_id missing — rule demands it.
                        "account_path": "Despesas > Aluguel",
                    }],
                },
            },
            "substitutions_applied": [],
            "python_errors": [], "database_errors": [],
            "substitution_errors": [], "warnings": [],
            "sheets_processed": ["Transaction"],
        }
        with mock.patch("multitenancy.imports_v2.services.ETLPipelineService") as svc_cls:
            svc_cls.return_value.execute.return_value = etl_return
            resp = self.client.post(
                _url_etl_analyze(self.company.id),
                {
                    "file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]})),
                    "transformation_rule_id": str(self.rule.pk),
                    "auto_create_journal_entries": _json_dump(self.AUTO_JE_CONFIG),
                },
                format="multipart",
            )
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_AWAITING_RESOLVE)
        self.assertEqual(body["is_committable"], False)
        missing = [i for i in body["open_issues"] if i["type"] == "missing_etl_parameter"]
        self.assertEqual(len(missing), 1)
        i = missing[0]
        self.assertEqual(i["severity"], "error")
        self.assertEqual(i["location"]["expected_column"], "bank_account_id")
        self.assertEqual(i["location"]["role"], "bank_account_field")
        self.assertIn("present_columns", i["context"])
        # Present columns should include account_path + erp_id + date
        # but NOT bank_account_id — that's the point.
        self.assertNotIn("bank_account_id", i["context"]["present_columns"])

    def test_erp_id_conflict_in_transformed_rows(self):
        """erp_id_conflict detection runs on the POST-transform rows,
        not the raw file — so substitution fixes land before the
        detector fires."""
        etl_return = {
            "transformed_data": {
                "Transaction": {
                    "row_count": 2,
                    "rows": [
                        {"__erp_id": "SHARED", "date": "2026-01-01", "amount": "100"},
                        {"__erp_id": "SHARED", "date": "2026-01-02", "amount": "200"},
                    ],
                },
            },
            "substitutions_applied": [],
            "python_errors": [], "database_errors": [],
            "substitution_errors": [], "warnings": [],
            "sheets_processed": ["Transaction"],
        }
        with mock.patch("multitenancy.imports_v2.services.ETLPipelineService") as svc_cls:
            svc_cls.return_value.execute.return_value = etl_return
            resp = self.client.post(
                _url_etl_analyze(self.company.id),
                {
                    "file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]})),
                    "transformation_rule_id": str(self.rule.pk),
                },
                format="multipart",
            )
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_AWAITING_RESOLVE)
        conflicts = [i for i in body["open_issues"] if i["type"] == "erp_id_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["location"]["erp_id"], "SHARED")

    def test_etl_service_exception_marks_session_error(self):
        with mock.patch("multitenancy.imports_v2.services.ETLPipelineService") as svc_cls:
            svc_cls.return_value.execute.side_effect = RuntimeError("boom")
            resp = self.client.post(
                _url_etl_analyze(self.company.id),
                {
                    "file": _upload_file(_build_xlsx({"Transaction": [{"date": "2026-01-01"}]})),
                    "transformation_rule_id": str(self.rule.pk),
                },
                format="multipart",
            )
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_ERROR)
        self.assertEqual(body["result"]["error"], "boom")
        self.assertEqual(body["result"]["stage"], "etl_execute")


@override_settings(AUTH_OFF=True)
class ETLv2CommitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Co")
        cls.user = User.objects.create_user(username="op", password="x")
        cls.rule = ImportTransformationRule.objects.create(
            company_id=cls.company.id,
            name="Test rule",
            source_sheet_name="Transaction",
            target_model="Transaction",
            column_mappings={"Data": "date"},
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_ready_etl_session(self) -> ImportSession:
        return ImportSession.objects.create(
            company_id=self.company.id,
            created_by=self.user,
            mode=ImportSession.MODE_ETL,
            status=ImportSession.STATUS_READY,
            transformation_rule=self.rule,
            file_name="ok.xlsx",
            file_bytes=b"<pretend xlsx>",
            parsed_payload={
                "transformed_data": {"Transaction": [{"amount": "100"}]},
                "substitutions_applied": [],
                "etl_errors": {},
            },
            config={"auto_create_journal_entries": {}},
            open_issues=[],
        )

    def test_commit_etl_session_reruns_etl_service_and_finalises(self):
        session = self._create_ready_etl_session()
        fake_result = {
            "transformed_data": {"Transaction": {"row_count": 1}},
            "would_create": {"Transaction": 1},
            "import_errors": [],
        }
        with mock.patch(
            "multitenancy.imports_v2.services.ETLPipelineService"
        ) as svc_cls:
            svc_cls.return_value.execute.return_value = fake_result
            resp = self.client.post(
                _url_etl_commit(self.company.id, session.pk), {}, format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_COMMITTED)
        # Phase 4A commit wraps the write-backend result with
        # ``substitution_rules_created`` (empty when no rules were staged).
        self.assertEqual(
            body["result"]["transformed_data"], fake_result["transformed_data"],
        )
        self.assertEqual(body["result"]["substitution_rules_created"], [])
        # Service constructed with commit=True
        _, kwargs = svc_cls.call_args
        self.assertTrue(kwargs["commit"])
        # file_bytes cleared post-commit
        session.refresh_from_db()
        self.assertIsNone(session.file_bytes)

    def test_commit_etl_session_without_file_bytes_returns_409(self):
        """If file_bytes was cleared (committed / discarded / TTL swept)
        we can't re-run the pipeline — surface as a not-ready error
        rather than crashing."""
        session = self._create_ready_etl_session()
        session.file_bytes = None
        session.save(update_fields=["file_bytes"])
        resp = self.client.post(
            _url_etl_commit(self.company.id, session.pk), {}, format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_session_detail_reachable_from_etl_namespace(self):
        """GET /api/core/etl/v2/sessions/<id>/ must work — same view as
        the template namespace, just mounted under a different prefix."""
        session = self._create_ready_etl_session()
        resp = self.client.get(_url_etl_session(self.company.id, session.pk))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["id"], session.pk)
        self.assertEqual(resp.json()["mode"], "etl")
