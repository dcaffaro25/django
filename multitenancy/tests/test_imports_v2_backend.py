"""Integration tests for the v2 template-import backend (Phase 2).

Covers:
  * Analyze happy path (clean file → session transitions to ``ready``).
  * Analyze detects erp_id conflicts and leaves the session in
    ``awaiting_resolve``.
  * Commit succeeds on a ``ready`` session (mocked write — execute_import_job
    is already tested elsewhere; here we only verify session lifecycle).
  * Commit refuses a session with blocking issues (409).
  * Discard transitions non-terminal sessions to ``discarded``.
  * Cross-tenant session IDs are hidden (404, not 403).

``execute_import_job`` is mocked because it needs full FK fixtures
(Entity, Currency, CostCenter, etc.) that are outside Phase 2's
surface area. Phase 4 tests will exercise the real write.
"""
from __future__ import annotations

import io
from unittest import mock

import pandas as pd
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from multitenancy.models import Company, ImportSession

User = get_user_model()


def _build_xlsx(sheets: dict) -> bytes:
    """Build a minimal .xlsx from {sheet_name: [row_dict, ...]}."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, rows in sheets.items():
            df = pd.DataFrame(rows or [{}])
            df.to_excel(xw, sheet_name=name, index=False)
    buf.seek(0)
    return buf.getvalue()


def _upload_file(content: bytes, name: str = "import.xlsx"):
    """Wrap bytes as a Django UploadedFile for multipart POST."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(
        name,
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# URLs we hit. Matching how nord_backend mounts multitenancy.urls under
# ``/<tenant_id>/``. In tests we use the company's id as tenant_id —
# the resolve helper falls back to user.company_id when that's not
# meaningful.
def _url_analyze(tenant_id):
    return f"/{tenant_id}/api/core/imports/v2/analyze/"


def _url_commit(tenant_id, pk):
    return f"/{tenant_id}/api/core/imports/v2/commit/{pk}/"


def _url_session(tenant_id, pk):
    return f"/{tenant_id}/api/core/imports/v2/sessions/{pk}/"


@override_settings(AUTH_OFF=True)  # sidestep token auth for these tests
class V2AnalyzeEndpointTests(TestCase):
    """analyze/ — file-to-session transitions."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Co")
        # CustomUser has no direct company_id FK — tenant resolution
        # happens via the URL path (``/<tenant_id>/...``) and
        # ``TenantMiddleware`` in prod. Tests rely on the URL resolving
        # the company, not on a user↔company FK.
        cls.user = User.objects.create_user(username="op", password="x")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_missing_file_returns_400(self):
        resp = self.client.post(_url_analyze(self.company.id), {}, format="multipart")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("file", (resp.json().get("error") or "").lower())

    def test_empty_file_returns_400(self):
        resp = self.client.post(
            _url_analyze(self.company.id),
            {"file": _upload_file(b"", "empty.xlsx")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_unreadable_file_marks_session_error(self):
        """Garbage bytes → session still created, status=error."""
        resp = self.client.post(
            _url_analyze(self.company.id),
            {"file": _upload_file(b"not a real xlsx", "bad.xlsx")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_ERROR)
        self.assertEqual(body["is_terminal"], True)
        self.assertIn("error", body.get("result") or {})

    def test_clean_file_transitions_to_ready(self):
        """A file with no transaction-sheet conflicts → ready, no issues."""
        xlsx = _build_xlsx({
            "Transaction": [
                {"__erp_id": "OMIE-1", "date": "2026-01-01",
                 "description": "x", "amount": "100.00"},
                {"__erp_id": "OMIE-2", "date": "2026-01-02",
                 "description": "y", "amount": "200.00"},
            ],
        })
        resp = self.client.post(
            _url_analyze(self.company.id),
            {"file": _upload_file(xlsx)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_READY)
        self.assertEqual(body["is_committable"], True)
        self.assertEqual(body["open_issues"], [])
        self.assertEqual(
            body["summary"],
            {"sheets": {"Transaction": 2}},
        )

    def test_erp_id_conflict_transitions_to_awaiting_resolve(self):
        """Two rows sharing an erp_id but disagreeing on date → one
        blocking issue; session stays in ``awaiting_resolve`` and
        is not committable."""
        xlsx = _build_xlsx({
            "Transaction": [
                {"__erp_id": "OMIE-1", "date": "2026-01-01",
                 "description": "x", "amount": "100.00"},
                {"__erp_id": "OMIE-1", "date": "2026-01-02",
                 "description": "x", "amount": "100.00"},
            ],
        })
        resp = self.client.post(
            _url_analyze(self.company.id),
            {"file": _upload_file(xlsx)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_AWAITING_RESOLVE)
        self.assertEqual(body["is_committable"], False)
        self.assertEqual(len(body["open_issues"]), 1)
        issue = body["open_issues"][0]
        self.assertEqual(issue["type"], "erp_id_conflict")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["location"]["sheet"], "Transaction")
        self.assertEqual(issue["location"]["erp_id"], "OMIE-1")
        self.assertIn("date", issue["context"]["fields"])
        self.assertIn("pick_row", issue["proposed_actions"])

    def test_non_transaction_sheets_do_not_trigger_erp_id_conflict_detection(self):
        """Journal entry or bank sheets can have shared erp_ids without
        the Phase 2 conflict detector firing (manual §11.10c scopes
        grouping to Transactions only)."""
        xlsx = _build_xlsx({
            "JournalEntry": [
                {"__erp_id": "SHARED", "debit_amount": "100", "credit_amount": 0},
                {"__erp_id": "SHARED", "debit_amount": 0, "credit_amount": "100"},
            ],
        })
        resp = self.client.post(
            _url_analyze(self.company.id),
            {"file": _upload_file(xlsx)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_READY)
        self.assertEqual(body["open_issues"], [])


@override_settings(AUTH_OFF=True)
class V2CommitEndpointTests(TestCase):
    """commit/ — session-lifecycle transitions."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="Acme Co")
        # CustomUser has no direct company_id FK — tenant resolution
        # happens via the URL path (``/<tenant_id>/...``) and
        # ``TenantMiddleware`` in prod. Tests rely on the URL resolving
        # the company, not on a user↔company FK.
        cls.user = User.objects.create_user(username="op", password="x")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _create_ready_session(self) -> ImportSession:
        return ImportSession.objects.create(
            company_id=self.company.id,
            created_by=self.user,
            mode=ImportSession.MODE_TEMPLATE,
            status=ImportSession.STATUS_READY,
            file_name="ok.xlsx",
            file_bytes=b"<pretend xlsx>",
            parsed_payload={"sheets": {"Transaction": [{"amount": "100"}]}},
            open_issues=[],
        )

    def _create_awaiting_resolve_session(self) -> ImportSession:
        return ImportSession.objects.create(
            company_id=self.company.id,
            created_by=self.user,
            mode=ImportSession.MODE_TEMPLATE,
            status=ImportSession.STATUS_AWAITING_RESOLVE,
            file_name="blocked.xlsx",
            file_bytes=b"<pretend xlsx>",
            parsed_payload={"sheets": {"Transaction": [{"amount": "100"}]}},
            open_issues=[{
                "issue_id": "iss-1",
                "type": "erp_id_conflict",
                "severity": "error",
                "location": {"sheet": "Transaction", "erp_id": "X"},
                "context": {"fields": {"date": ["a", "b"]}},
                "proposed_actions": ["pick_row"],
                "message": "conflict",
            }],
        )

    def test_commit_ready_session_calls_execute_import_job_and_finalises(self):
        session = self._create_ready_session()
        fake_result = {"imports": [{"model": "Transaction", "created": 1, "updated": 0}]}
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            return_value=fake_result,
        ) as mocked:
            resp = self.client.post(
                _url_commit(self.company.id, session.pk), {}, format="json",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["status"], ImportSession.STATUS_COMMITTED)
        self.assertEqual(body["result"], fake_result)
        self.assertIsNotNone(body["committed_at"])
        # And ``execute_import_job`` was called with the session's data.
        call_kwargs = mocked.call_args.kwargs
        self.assertEqual(call_kwargs["company_id"], self.company.id)
        self.assertTrue(call_kwargs["commit"])
        self.assertEqual(
            [s["model"] for s in call_kwargs["sheets"]], ["Transaction"],
        )

        # file_bytes cleared after commit — no hoarding.
        session.refresh_from_db()
        self.assertIsNone(session.file_bytes)

    def test_commit_blocked_session_returns_409(self):
        session = self._create_awaiting_resolve_session()
        resp = self.client.post(
            _url_commit(self.company.id, session.pk), {}, format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertIn("not ready", body["error"].lower())
        self.assertEqual(body["status"], ImportSession.STATUS_AWAITING_RESOLVE)

    def test_commit_already_committed_session_returns_409(self):
        session = self._create_ready_session()
        session.status = ImportSession.STATUS_COMMITTED
        session.save(update_fields=["status"])
        resp = self.client.post(
            _url_commit(self.company.id, session.pk), {}, format="json",
        )
        self.assertEqual(resp.status_code, 409, resp.content)

    def test_commit_failure_marks_session_error(self):
        """When ``execute_import_job`` raises, the session should end up
        in ``error`` status with the traceback captured on ``result``."""
        session = self._create_ready_session()
        with mock.patch(
            "multitenancy.imports_v2.services.execute_import_job",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.post(
                _url_commit(self.company.id, session.pk), {}, format="json",
            )
        self.assertEqual(resp.status_code, 500, resp.content)
        session.refresh_from_db()
        self.assertEqual(session.status, ImportSession.STATUS_ERROR)
        self.assertEqual(session.result.get("error"), "boom")


@override_settings(AUTH_OFF=True)
class V2SessionDetailTests(TestCase):
    """GET + DELETE /sessions/<id>/."""

    @classmethod
    def setUpTestData(cls):
        cls.co1 = Company.objects.create(name="Acme Co")
        cls.co2 = Company.objects.create(name="Globex Co")
        cls.user1 = User.objects.create_user(username="op1", password="x")
        cls.user2 = User.objects.create_user(username="op2", password="x")

    def _make_session(self, company):
        return ImportSession.objects.create(
            company_id=company.id,
            mode=ImportSession.MODE_TEMPLATE,
            status=ImportSession.STATUS_AWAITING_RESOLVE,
            file_name="x",
            parsed_payload={"sheets": {}},
        )

    def test_get_returns_own_session(self):
        session = self._make_session(self.co1)
        client = APIClient()
        client.force_authenticate(self.user1)
        resp = client.get(_url_session(self.co1.id, session.pk))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["id"], session.pk)

    def test_get_other_tenants_session_returns_404(self):
        """Cross-tenant reads must return 404 — we don't even confirm the
        id exists in another tenant's space."""
        session = self._make_session(self.co1)
        client = APIClient()
        client.force_authenticate(self.user2)
        resp = client.get(_url_session(self.co2.id, session.pk))
        self.assertEqual(resp.status_code, 404)

    def test_delete_transitions_to_discarded(self):
        session = self._make_session(self.co1)
        client = APIClient()
        client.force_authenticate(self.user1)
        resp = client.delete(_url_session(self.co1.id, session.pk))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], ImportSession.STATUS_DISCARDED)

    def test_delete_already_committed_is_noop(self):
        session = self._make_session(self.co1)
        session.status = ImportSession.STATUS_COMMITTED
        session.save(update_fields=["status"])
        client = APIClient()
        client.force_authenticate(self.user1)
        resp = client.delete(_url_session(self.co1.id, session.pk))
        # Terminal sessions don't change state — still committed.
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["status"], ImportSession.STATUS_COMMITTED)
