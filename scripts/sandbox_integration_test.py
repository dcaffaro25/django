"""
End-to-end integration test for the pipeline sandbox endpoint.

Spins up a tiny in-process mock Omie HTTP server, seeds fixtures via
Django ORM, exercises POST /{tenant}/api/pipeline-sandbox/ through a
real DRF test client, and prints the response. No network, no browser.

Run from the worktree root:
  python scripts/sandbox_integration_test.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")

import django
django.setup()

from django.test import Client
from rest_framework.authtoken.models import Token

from multitenancy.models import Company, CustomUser
from erp_integrations.models import (
    ERPAPIDefinition,
    ERPConnection,
    ERPProvider,
)


STEP1_BODY = {
    "pagina": 1,
    "total_de_paginas": 1,
    "total_de_registros": 3,
    "registros": 3,
    "clientes_cadastro": [
        {"codigo": "C1", "nome": "Alpha LTDA"},
        {"codigo": "C2", "nome": "Beta SA"},
        {"codigo": "C3", "nome": "Gamma ME"},
    ],
}

# Step 2 returns one record per fanout call with its own fields.
STEP2_DETAILS = {
    "C1": {"codigo": "C1", "nome": "Alpha LTDA", "cnpj_cpf": "11.111.111/0001-11", "cidade": "SP"},
    "C2": {"codigo": "C2", "nome": "Beta SA", "cnpj_cpf": "22.222.222/0001-22", "cidade": "RJ"},
    "C3": {"codigo": "C3", "nome": "Gamma ME", "cnpj_cpf": "33.333.333/0001-33", "cidade": "BH"},
}


class MockOmieHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 — stdlib convention
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}

        call = payload.get("call", "")
        # Discriminate by the URL path for clarity.
        if self.path.endswith("/clientes"):
            body = STEP1_BODY
        elif self.path.endswith("/cliente"):
            codigo = None
            params = payload.get("param") or []
            if isinstance(params, list) and params:
                codigo = (params[0] or {}).get("codigo")
            body = STEP2_DETAILS.get(str(codigo), {"codigo": codigo, "nome": "?"})
        else:
            body = {"call": call, "echoed": payload}

        data = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args, **_kwargs):  # silence default logging
        return


def start_mock_server(port: int) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", port), MockOmieHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def seed_fixtures(mock_port: int):
    uid = uuid.uuid4().hex[:6]
    subdomain = f"sbx-{uid}"
    company, _ = Company.objects.get_or_create(name=f"Sandbox E2E {uid}", defaults={"subdomain": subdomain})
    # Company.save() auto-generates a unique subdomain if blank; force-set ours for predictability.
    if company.subdomain != subdomain:
        company.subdomain = subdomain
        company.save(update_fields=["subdomain"])

    user, _ = CustomUser.objects.get_or_create(
        username=f"sbx-user-{uid}",
        defaults={"is_superuser": True, "is_staff": True},
    )
    user.is_superuser = True
    user.is_staff = True
    user.save(update_fields=["is_superuser", "is_staff"])
    token, _ = Token.objects.get_or_create(user=user)

    provider, _ = ERPProvider.objects.get_or_create(
        slug=f"mock-omie-{uid}", defaults={"name": f"Mock Omie {uid}"}
    )
    connection = ERPConnection.objects.create(
        company=company, provider=provider, app_key="mock-key", app_secret="mock-secret", name="Mock conn"
    )
    api_def_list = ERPAPIDefinition.objects.create(
        provider=provider,
        call="ListarClientes",
        url=f"http://127.0.0.1:{mock_port}/clientes",
        method="POST",
        transform_config={"records": {"path": "clientes_cadastro"}},
        description="Mock list",
    )
    api_def_detail = ERPAPIDefinition.objects.create(
        provider=provider,
        call="ConsultarCliente",
        url=f"http://127.0.0.1:{mock_port}/cliente",
        method="POST",
        transform_config={"records": {"rootAsOneRow": True, "autoDiscover": False}},
        description="Mock detail",
    )
    return {
        "company": company,
        "subdomain": subdomain,
        "token": token,
        "connection": connection,
        "api_def_list": api_def_list,
        "api_def_detail": api_def_detail,
    }


def main():
    port = 9912
    server = start_mock_server(port)
    print(f"Mock Omie server listening on 127.0.0.1:{port}")

    fx = seed_fixtures(port)
    print(f"Seeded company={fx['company'].id} subdomain={fx['subdomain']} connection={fx['connection'].id}")

    client = Client(HTTP_AUTHORIZATION=f"Token {fx['token'].key}")

    # Case 1: Single-step sandbox — prove the page-1 preview pipeline works.
    body1 = {
        "connection_id": fx["connection"].id,
        "steps": [
            {"order": 1, "api_definition_id": fx["api_def_list"].id},
        ],
    }
    r1 = client.post(
        f"/{fx['subdomain']}/api/pipeline-sandbox/",
        data=json.dumps(body1),
        content_type="application/json",
    )
    print(f"\n--- Case 1: single step ---\nstatus={r1.status_code}")
    print(json.dumps(r1.json(), indent=2, default=str)[:1200])

    # Case 2: Two-step fanout — clientes[*].codigo → ConsultarCliente once per id.
    body2 = {
        "connection_id": fx["connection"].id,
        "steps": [
            {"order": 1, "api_definition_id": fx["api_def_list"].id},
            {
                "order": 2,
                "api_definition_id": fx["api_def_detail"].id,
                "param_bindings": [
                    {
                        "mode": "fanout",
                        "source_step": 1,
                        "expression": "clientes_cadastro[*].codigo",
                        "into": "codigo",
                    }
                ],
                "select_fields": "[*].{id: codigo, city: cidade}",
            },
        ],
    }
    r2 = client.post(
        f"/{fx['subdomain']}/api/pipeline-sandbox/",
        data=json.dumps(body2),
        content_type="application/json",
    )
    print(f"\n--- Case 2: two-step fanout + projection ---\nstatus={r2.status_code}")
    data2 = r2.json()
    print(f"success={data2.get('success')} status={data2.get('status')}")
    print(f"records_extracted={data2.get('records_extracted')}")
    print(f"first payload (redacted) call={data2.get('first_payload_redacted', {}).get('call')}")
    print(f"caps={data2.get('caps')}")
    print("per-step:")
    for s in (data2.get("diagnostics") or {}).get("steps", []):
        print(
            f"  step {s['order']} ({s['api_call']}): "
            f"extracted={s['extracted']} pages={s['pages']} "
            f"fanout={s.get('fanout')}"
        )
    print("projections from step 2:")
    for s in data2.get("preview_by_step", []):
        if s["order"] == 2:
            print(json.dumps(s.get("projected"), indent=2, default=str))

    # Case 3: Validation failure — jmespath referencing a future step should 400.
    body3 = {
        "connection_id": fx["connection"].id,
        "steps": [
            {
                "order": 1,
                "api_definition_id": fx["api_def_list"].id,
                "param_bindings": [
                    {"mode": "jmespath", "source_step": 2, "expression": "x", "into": "y"}
                ],
            },
        ],
    }
    r3 = client.post(
        f"/{fx['subdomain']}/api/pipeline-sandbox/",
        data=json.dumps(body3),
        content_type="application/json",
    )
    print(f"\n--- Case 3: validation error (self/forward reference) ---\nstatus={r3.status_code}")
    print(json.dumps(r3.json(), indent=2, default=str))

    server.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
