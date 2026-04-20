"""
Seed dev data for browser-based sandbox testing.

Creates (or reuses) a superuser, a Company with known subdomain, a token,
an ERPProvider + ERPConnection, and two ERPAPIDefinitions pointing at the
local mock Omie server. Prints the token + tenant subdomain so they can
be dropped into frontend .env (VITE_DEV_TOKEN, VITE_DEFAULT_TENANT).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")

import django  # noqa: E402
django.setup()

from multitenancy.models import Company  # noqa: E402
from erp_integrations.models import (  # noqa: E402
    ERPAPIDefinition,
    ERPConnection,
    ERPProvider,
)

MOCK_PORT = 9912
TENANT_SUB = os.environ.get("SANDBOX_TENANT", "datbaby")


def main():
    company = Company.objects.filter(subdomain=TENANT_SUB).first()
    if company is None:
        print(f"ERROR: no company with subdomain={TENANT_SUB!r}. Set SANDBOX_TENANT=<existing subdomain>.")
        sys.exit(1)
    print(f"Company #{company.id} subdomain={company.subdomain} (reused)")

    provider, _ = ERPProvider.objects.get_or_create(
        slug="mock-omie-dev",
        defaults={"name": "Mock Omie (dev)"},
    )

    connection, _ = ERPConnection.objects.get_or_create(
        company=company,
        provider=provider,
        defaults={"app_key": "dev-key", "app_secret": "dev-secret", "name": "Mock dev conn"},
    )
    print(f"Connection #{connection.id}")

    list_def, _ = ERPAPIDefinition.objects.update_or_create(
        provider=provider,
        call="ListarClientes",
        defaults={
            "url": f"http://127.0.0.1:{MOCK_PORT}/clientes",
            "method": "POST",
            "transform_config": {"records": {"path": "clientes_cadastro"}},
            "description": "Mock: list clientes",
            "is_active": True,
        },
    )
    detail_def, _ = ERPAPIDefinition.objects.update_or_create(
        provider=provider,
        call="ConsultarCliente",
        defaults={
            "url": f"http://127.0.0.1:{MOCK_PORT}/cliente",
            "method": "POST",
            "transform_config": {"records": {"rootAsOneRow": True, "autoDiscover": False}},
            "description": "Mock: detail cliente",
            "is_active": True,
        },
    )
    print(f"API defs: #{list_def.id} ListarClientes, #{detail_def.id} ConsultarCliente")
    print(f"\nTenant ready: /{TENANT_SUB}/api/pipeline-sandbox/")


if __name__ == "__main__":
    main()
