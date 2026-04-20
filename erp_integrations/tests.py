from __future__ import annotations

import hashlib
import uuid
from typing import Optional
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from multitenancy.models import Company, CustomUser

from .models import (
    ERPAPIDefinition,
    ERPConnection,
    ERPProvider,
    ERPRawRecord,
    ERPSyncJob,
    ERPSyncPipeline,
    ERPSyncPipelineRun,
    ERPSyncPipelineStep,
    ERPSyncRun,
)


def _hash64(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _create_chain(company: Company):
    uid = uuid.uuid4().hex[:10]
    provider = ERPProvider.objects.create(slug=f"omie-{uid}", name="Omie Test")
    conn = ERPConnection.objects.create(
        company=company,
        provider=provider,
        app_key="k",
        app_secret="secret",
    )
    api_def = ERPAPIDefinition.objects.create(
        provider=provider,
        call="ListarTest",
        url="https://example.com/api",
        method="POST",
    )
    job = ERPSyncJob.objects.create(
        connection=conn,
        api_definition=api_def,
        name="test-job",
        company=company,
    )
    run = ERPSyncRun.objects.create(job=job, company=company, status="completed")
    return run


def _create_raw_record(
    company: Company,
    sync_run: ERPSyncRun,
    *,
    data: dict,
    api_call: str = "ListarTest",
    page_header: Optional[dict] = None,
    record_hash: Optional[str] = None,
) -> ERPRawRecord:
    rh = record_hash or _hash64(str(data))
    return ERPRawRecord.objects.create(
        company=company,
        sync_run=sync_run,
        api_call=api_call,
        page_number=1,
        record_index=0,
        global_index=0,
        page_records_count=1,
        total_pages=1,
        total_records=1,
        page_response_header=page_header or {"nPagina": 1},
        data=data,
        record_hash=rh,
    )


class ERPRawRecordDataAPITests(APITestCase):
    """GET /{tenant}/api/raw-records/data/"""

    def setUp(self):
        self.company_a = Company.objects.create(name="ERP Co A", subdomain="erp-test-a")
        self.company_b = Company.objects.create(name="ERP Co B", subdomain="erp-test-b")
        self.user = CustomUser.objects.create_user(username="erp_api_user", password="x")
        self.client.force_authenticate(user=self.user)

        self.run_a = _create_chain(self.company_a)
        self.run_b = _create_chain(self.company_b)

        _create_raw_record(
            self.company_a,
            self.run_a,
            data={"codigo": 100, "nested": {"k": "alpha"}},
            page_header={"nPagina": 1, "tag": "x"},
        )
        _create_raw_record(
            self.company_a,
            self.run_a,
            data={"codigo": 200, "nested": {"k": "beta"}},
            record_hash=_hash64("second"),
        )
        _create_raw_record(
            self.company_b,
            self.run_b,
            data={"codigo": 300},
        )

    def _url(self, company: Company, query: Optional[dict] = None):
        base = reverse("erp-raw-record-data", kwargs={"tenant_id": company.subdomain})
        if not query:
            return base
        return f"{base}?{urlencode(query)}"

    def test_tenant_scope_only_sees_own_company_data(self):
        url = self._url(self.company_a)
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("results", r.data)
        codes = {row.get("codigo") for row in r.data["results"]}
        self.assertEqual(codes, {100, 200})
        self.assertNotIn(300, codes)

    def test_filter_model_field_api_call(self):
        extra_run = _create_chain(self.company_a)
        _create_raw_record(
            self.company_a,
            extra_run,
            data={"x": 1},
            api_call="OtherCall",
            record_hash=_hash64("othercall"),
        )
        url = self._url(self.company_a, {"api_call": "ListarTest"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        codes = {row.get("codigo") for row in r.data["results"] if "codigo" in row}
        self.assertEqual(codes, {100, 200})

    def test_filter_data_nested_path(self):
        url = self._url(self.company_a, {"data__nested__k": "alpha"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["codigo"], 100)

    def test_filter_page_response_header(self):
        url = self._url(self.company_a, {"page_response_header__tag": "x"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 1)
        self.assertEqual(r.data["results"][0]["codigo"], 100)

    def test_paginated_false_plain_array_with_limit(self):
        url = self._url(self.company_a, {"paginated": "false", "limit": "1"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIsInstance(r.data, list)
        self.assertEqual(len(r.data), 1)

    def test_plain_array_limit_too_high_returns_400(self):
        url = self._url(self.company_a, {"paginated": "false", "limit": "9999"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_json_path_segment_returns_400(self):
        url = self._url(self.company_a, {"data__bad-key": "1"})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


def _mock_response(payload: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _pipeline_fixture(company: Company, provider_slug: Optional[str] = None):
    """
    Build a minimal provider + connection + two api defs (step1 + step2) for
    pipeline tests. Returns (connection, api_def_step1, api_def_step2).
    """
    uid = uuid.uuid4().hex[:8]
    provider = ERPProvider.objects.create(
        slug=provider_slug or f"omie-pipe-{uid}", name=f"Omie Pipe {uid}"
    )
    conn = ERPConnection.objects.create(
        company=company, provider=provider, app_key="ak", app_secret="sk"
    )
    api_def_step1 = ERPAPIDefinition.objects.create(
        provider=provider,
        call="ListarClientes",
        url="https://example.com/api/clientes",
        method="POST",
        transform_config={"records": {"path": "clientes_cadastro"}},
    )
    api_def_step2 = ERPAPIDefinition.objects.create(
        provider=provider,
        call="ConsultarCliente",
        url="https://example.com/api/cliente",
        method="POST",
        transform_config={"records": {"rootAsOneRow": True, "autoDiscover": False}},
    )
    return conn, api_def_step1, api_def_step2


class PipelineBindingResolutionTests(TestCase):
    """Unit tests for binding validation and resolution."""

    def test_static_binding_applied(self):
        from .services.pipeline_service import _resolve_non_fanout_bindings

        overrides, fanout, log = _resolve_non_fanout_bindings(
            [{"mode": "static", "into": "codigo", "value": 42}],
            context={},
        )
        self.assertEqual(overrides, {"codigo": 42})
        self.assertIsNone(fanout)
        self.assertEqual(log[0]["mode"], "static")

    def test_jmespath_binding_single_value(self):
        from .services.pipeline_service import _resolve_non_fanout_bindings

        overrides, fanout, _ = _resolve_non_fanout_bindings(
            [
                {
                    "mode": "jmespath",
                    "source_step": 1,
                    "expression": "clientes[0].codigo",
                    "into": "codigo",
                }
            ],
            context={1: {"clientes": [{"codigo": "C1"}, {"codigo": "C2"}]}},
        )
        self.assertEqual(overrides, {"codigo": "C1"})
        self.assertIsNone(fanout)

    def test_fanout_binding_kept_separate(self):
        from .services.pipeline_service import _resolve_non_fanout_bindings

        overrides, fanout, _ = _resolve_non_fanout_bindings(
            [
                {"mode": "static", "into": "x", "value": 1},
                {
                    "mode": "fanout",
                    "source_step": 1,
                    "expression": "items[*].id",
                    "into": "id",
                },
            ],
            context={1: {"items": [{"id": "A"}, {"id": "B"}]}},
        )
        self.assertEqual(overrides, {"x": 1})
        self.assertIsNotNone(fanout)
        self.assertEqual(fanout["into"], "id")

    def test_two_fanouts_rejected(self):
        from .services.pipeline_service import (
            PipelineConfigError,
            _resolve_non_fanout_bindings,
        )

        with self.assertRaises(PipelineConfigError):
            _resolve_non_fanout_bindings(
                [
                    {"mode": "fanout", "source_step": 1, "expression": "a[*]", "into": "x"},
                    {"mode": "fanout", "source_step": 1, "expression": "b[*]", "into": "y"},
                ],
                context={1: {"a": [1], "b": [2]}},
            )

    def test_validate_binding_rejects_self_reference(self):
        from .services.pipeline_service import PipelineConfigError, _validate_binding

        with self.assertRaises(PipelineConfigError):
            _validate_binding(
                {
                    "mode": "jmespath",
                    "source_step": 2,
                    "expression": "x",
                    "into": "y",
                },
                step_order=2,
            )

    def test_validate_binding_rejects_unknown_mode(self):
        from .services.pipeline_service import PipelineConfigError, _validate_binding

        with self.assertRaises(PipelineConfigError):
            _validate_binding({"mode": "weird", "into": "y"}, step_order=1)


class ExecutePipelineTests(TestCase):
    """End-to-end tests of the executor with mocked HTTP."""

    def setUp(self):
        self.company = Company.objects.create(name="Pipe Co", subdomain="pipe-co-test")
        self.conn, self.api1, self.api2 = _pipeline_fixture(self.company)

    def _build_pipeline(self, bindings_step2):
        pipeline = ERPSyncPipeline.objects.create(
            connection=self.conn,
            company=self.company,
            name="cli + details",
        )
        ERPSyncPipelineStep.objects.create(
            pipeline=pipeline,
            order=1,
            api_definition=self.api1,
            extra_params={},
            param_bindings=[],
        )
        ERPSyncPipelineStep.objects.create(
            pipeline=pipeline,
            order=2,
            api_definition=self.api2,
            extra_params={},
            param_bindings=bindings_step2,
        )
        return pipeline

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_fanout_runs_step_once_per_value_and_persists(self, mock_post):
        from .services.pipeline_service import execute_pipeline

        pipeline = self._build_pipeline(
            [
                {
                    "mode": "fanout",
                    "source_step": 1,
                    "expression": "clientes_cadastro[*].codigo",
                    "into": "codigo",
                }
            ]
        )
        step1_response = {
            "pagina": 1,
            "total_de_paginas": 1,
            "total_de_registros": 2,
            "registros": 2,
            "clientes_cadastro": [{"codigo": "A1"}, {"codigo": "A2"}],
        }
        detail_a1 = {"codigo": "A1", "nome": "Alpha"}
        detail_a2 = {"codigo": "A2", "nome": "Beta"}

        mock_post.side_effect = [
            _mock_response(step1_response),
            _mock_response(detail_a1),
            _mock_response(detail_a2),
        ]

        out = execute_pipeline(pipeline.id, dry_run=False)

        self.assertTrue(out["success"], out)
        self.assertEqual(out["status"], "completed")
        self.assertEqual(mock_post.call_count, 3)
        payloads = [call.kwargs["json"] for call in mock_post.call_args_list]
        self.assertEqual(payloads[0]["call"], "ListarClientes")
        self.assertEqual(payloads[1]["call"], "ConsultarCliente")
        self.assertEqual(payloads[1]["param"][0]["codigo"], "A1")
        self.assertEqual(payloads[2]["param"][0]["codigo"], "A2")

        pipe_run = ERPSyncPipelineRun.objects.get(pk=out["run_id"])
        raw_for_run = ERPRawRecord.objects.filter(pipeline_run=pipe_run)
        self.assertEqual(raw_for_run.count(), 4)  # 2 from step1 + 2 from step2

        steps_present = set(raw_for_run.values_list("pipeline_step_order", flat=True))
        self.assertEqual(steps_present, {1, 2})

        for row in raw_for_run:
            self.assertIsNone(row.sync_run_id)

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_dry_run_does_not_persist_raw_records(self, mock_post):
        from .services.pipeline_service import execute_pipeline

        pipeline = self._build_pipeline(
            [
                {
                    "mode": "jmespath",
                    "source_step": 1,
                    "expression": "clientes_cadastro[0].codigo",
                    "into": "codigo",
                }
            ]
        )
        step1_response = {
            "pagina": 1,
            "total_de_paginas": 1,
            "total_de_registros": 1,
            "registros": 1,
            "clientes_cadastro": [{"codigo": "X1"}],
        }
        detail = {"codigo": "X1", "nome": "X"}
        mock_post.side_effect = [_mock_response(step1_response), _mock_response(detail)]

        out = execute_pipeline(pipeline.id, dry_run=True)

        self.assertEqual(out["status"], "completed")
        self.assertEqual(ERPRawRecord.objects.filter(pipeline_run_id=out["run_id"]).count(), 0)
        self.assertEqual(len(out["preview_by_step"]), 2)
        self.assertEqual(out["preview_by_step"][0]["row_count"], 1)
        self.assertEqual(out["preview_by_step"][1]["row_count"], 1)

        pipeline.refresh_from_db()
        self.assertEqual(pipeline.last_run_status, "never")  # dry_run must not update

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_failed_step_marks_run_failed_and_stops(self, mock_post):
        from .services.pipeline_service import execute_pipeline
        import requests as _req

        pipeline = self._build_pipeline(
            [
                {
                    "mode": "fanout",
                    "source_step": 1,
                    "expression": "clientes_cadastro[*].codigo",
                    "into": "codigo",
                }
            ]
        )
        step1_response = {
            "pagina": 1,
            "total_de_paginas": 1,
            "total_de_registros": 1,
            "registros": 1,
            "clientes_cadastro": [{"codigo": "Z1"}],
        }
        error_resp = MagicMock()
        error_resp.status_code = 400
        error_resp.raise_for_status.side_effect = _req.HTTPError("boom")

        def side(*args, **kwargs):
            if side.calls == 0:
                side.calls += 1
                return _mock_response(step1_response)
            side.calls += 1
            return error_resp

        side.calls = 0
        mock_post.side_effect = side

        out = execute_pipeline(pipeline.id, dry_run=False)

        self.assertEqual(out["failed_step_order"], 2)
        self.assertIn(out["status"], {"partial", "failed"})
        # Step 1 persisted 1 record before step 2 failed
        self.assertEqual(
            ERPRawRecord.objects.filter(pipeline_run_id=out["run_id"]).count(),
            1,
        )


class PipelineSandboxEndpointTests(APITestCase):
    """POST /{tenant}/api/pipeline-sandbox/ — preview-only execution."""

    def setUp(self):
        self.company = Company.objects.create(name="Sandbox Co", subdomain="sandbox-co-test")
        self.user = CustomUser.objects.create_user(username="sandbox_user", password="x")
        self.client.force_authenticate(user=self.user)
        self.conn, self.api1, self.api2 = _pipeline_fixture(self.company)

    def _url(self):
        return f"/{self.company.subdomain}/api/pipeline-sandbox/"

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_sandbox_does_not_persist_records_or_pipeline(self, mock_post):
        step1_response = {
            "pagina": 1,
            "total_de_paginas": 1,
            "total_de_registros": 1,
            "registros": 1,
            "clientes_cadastro": [{"codigo": "S1", "nome": "Foo"}],
        }
        mock_post.side_effect = [_mock_response(step1_response)]

        body = {
            "connection_id": self.conn.id,
            "steps": [
                {
                    "order": 1,
                    "api_definition_id": self.api1.id,
                    "extra_params": {},
                    "param_bindings": [],
                }
            ],
        }
        r = self.client.post(self._url(), body, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        self.assertEqual(r.data["records_extracted"], 1)
        self.assertEqual(len(r.data["preview_by_step"]), 1)
        self.assertEqual(r.data["preview_by_step"][0]["row_count"], 1)

        # No pipeline or raw records should be persisted.
        self.assertEqual(ERPSyncPipeline.objects.count(), 0)
        self.assertEqual(ERPSyncPipelineRun.objects.count(), 0)
        self.assertEqual(ERPRawRecord.objects.count(), 0)

        # App_key/app_secret redacted in returned payload.
        self.assertEqual(r.data["first_payload_redacted"]["app_key"], "***REDACTED***")

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_sandbox_respects_default_caps(self, mock_post):
        step1 = {
            "pagina": 1,
            "total_de_paginas": 1,
            "total_de_registros": 3,
            "registros": 3,
            "clientes_cadastro": [
                {"codigo": "C1"},
                {"codigo": "C2"},
                {"codigo": "C3"},
            ],
        }
        # Three fanout values against step 2; cap max_fanout=2 should limit to 2 calls.
        responses = [
            _mock_response(step1),
            _mock_response({"codigo": "C1"}),
            _mock_response({"codigo": "C2"}),
        ]
        mock_post.side_effect = responses

        body = {
            "connection_id": self.conn.id,
            "max_fanout": 2,
            "steps": [
                {
                    "order": 1,
                    "api_definition_id": self.api1.id,
                },
                {
                    "order": 2,
                    "api_definition_id": self.api2.id,
                    "param_bindings": [
                        {
                            "mode": "fanout",
                            "source_step": 1,
                            "expression": "clientes_cadastro[*].codigo",
                            "into": "codigo",
                        }
                    ],
                },
            ],
        }
        r = self.client.post(self._url(), body, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK, r.content)
        # 1 + 2 = 3 HTTP calls due to max_fanout cap.
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(r.data["caps"]["max_fanout"], 2)

    def test_sandbox_rejects_bad_provider_api_def(self):
        other_provider = ERPProvider.objects.create(slug="other-prov", name="Other")
        api_def_other = ERPAPIDefinition.objects.create(
            provider=other_provider,
            call="Foo",
            url="https://example.com/foo",
        )
        body = {
            "connection_id": self.conn.id,
            "steps": [{"order": 1, "api_definition_id": api_def_other.id}],
        }
        r = self.client.post(self._url(), body, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", r.data)


class BackwardCompatibilityTests(TestCase):
    """Ensure the single-job sync path still works after the shared helper refactor."""

    def setUp(self):
        self.company = Company.objects.create(name="BC Co", subdomain="bc-co-test")
        uid = uuid.uuid4().hex[:8]
        provider = ERPProvider.objects.create(slug=f"bc-omie-{uid}", name="BC Omie")
        self.conn = ERPConnection.objects.create(
            company=self.company, provider=provider, app_key="k", app_secret="s"
        )
        self.api_def = ERPAPIDefinition.objects.create(
            provider=provider,
            call="ListarBC",
            url="https://example.com/bc",
            transform_config={"records": {"path": "linhas"}},
        )
        self.job = ERPSyncJob.objects.create(
            connection=self.conn,
            api_definition=self.api_def,
            name="bc-job",
            company=self.company,
        )

    @patch("erp_integrations.services.omie_sync_service.requests.post")
    def test_execute_sync_still_persists_records_via_shared_helper(self, mock_post):
        from .services.omie_sync_service import execute_sync

        mock_post.return_value = _mock_response(
            {
                "pagina": 1,
                "total_de_paginas": 1,
                "total_de_registros": 2,
                "registros": 2,
                "linhas": [{"id": 1}, {"id": 2}],
            }
        )
        out = execute_sync(self.job.id, dry_run=False)

        self.assertTrue(out["success"], out)
        run = ERPSyncRun.objects.get(pk=out["run_id"])
        self.assertEqual(run.records_stored, 2)
        # All records are linked to sync_run and NOT to any pipeline_run.
        records = ERPRawRecord.objects.filter(sync_run=run)
        self.assertEqual(records.count(), 2)
        self.assertTrue(all(r.pipeline_run_id is None for r in records))
