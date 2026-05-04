"""Probe call-name candidates for the pedido-venda + complementary endpoints.

Enrichment scenario: list pedidos, then drill into each via complementary
detail calls (cliente, produto, NF). Need to confirm which call names
Omie actually accepts so the pipeline test runs cleanly.
"""
import requests

import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from erp_integrations.models import ERPConnection

conn = ERPConnection.objects.filter(company_id=5, provider__slug="omie").first()


def t(url, call, params):
    payload = {
        "call": call, "param": [params],
        "app_key": conn.app_key, "app_secret": conn.app_secret,
    }
    r = requests.post(url, json=payload, timeout=20)
    body = {}
    try:
        body = r.json()
    except Exception:
        pass
    msg = body.get("message") or body.get("faultstring") or "<ok>"
    return r.status_code, msg


def probe(url, candidates, params):
    label = url.rstrip("/").rsplit("/", 1)[-1]
    print(f"\n--- {label} ---")
    for c in candidates:
        s, msg = t(url, c, params)
        ok = (s == 200) or (s == 500 and "tag" in str(msg).lower() and "não faz parte" in str(msg).lower())
        marker = "OK" if ok else "NO"
        print(f"  [{marker}] {c:34s} status={s} {str(msg)[:90]}")
        if ok:
            return c
    return None


# --- ConsultarPedidoVenda + variants  (URL = /produtos/pedidovenda/)
probe(
    "https://app.omie.com.br/api/v1/produtos/pedidovenda/",
    ["ConsultarPedidoVenda", "ListarPedidoVendaResumido", "ListarPedidosResumido",
     "ListarPedidoResumido", "PesquisarPedidoVenda",
     "ConsultarPedidosVenda", "ConsultarResumoPedidoVenda"],
    {"nPagina": 1, "nRegPorPagina": 5},
)

# --- Try with snake_case pagination too
probe(
    "https://app.omie.com.br/api/v1/produtos/pedidovenda/",
    ["ConsultarPedidoVenda", "ListarPedidoVendaResumido", "ListarPedidosResumido"],
    {"pagina": 1, "registros_por_pagina": 5},
)

# --- Enrichment: ConsultarPedido (full pedido with items) — at /produtos/pedido/
probe(
    "https://app.omie.com.br/api/v1/produtos/pedido/",
    ["ConsultarPedido"],
    {"codigo_pedido": 1},
)

# --- ConsultarCliente — at /geral/clientes/
probe(
    "https://app.omie.com.br/api/v1/geral/clientes/",
    ["ConsultarCliente"],
    {"codigo_cliente_omie": 1},
)

# --- ConsultarProduto — at /geral/produtos/
probe(
    "https://app.omie.com.br/api/v1/geral/produtos/",
    ["ConsultarProduto"],
    {"codigo_produto": 1},
)

# --- ConsultarNF — at /produtos/nfconsultar/  (already known)
probe(
    "https://app.omie.com.br/api/v1/produtos/nfconsultar/",
    ["ConsultarNF"],
    {"nIdNF": 1},
)
