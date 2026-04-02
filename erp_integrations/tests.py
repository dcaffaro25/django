from __future__ import annotations

import hashlib
import uuid
from typing import Optional
from urllib.parse import urlencode

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
