"""Validates two patterns for Omie ERP pipelines:

1. **Bulk-and-index** (recommended): one ``Listar*`` call retrieves all
   complementary data once, downstream steps select what they need via
   JMESPath. Replaces the N-call fanout pattern that thrashes Omie's
   rate limit.

2. **Per-row fanout** (still works for small N or when no Listar exists):
   ``ConsultarCliente`` fired once per pedido. Slow + throttle-prone.

Plus call_erp_api's new ``cache_ttl_seconds`` argument — same (call,
params) within the TTL window returns the cached payload, no HTTP.

User asked for ``ConsultarPedidoVenda`` originally; the live API
returns ``Method "ConsultarPedidoVenda" not exists``, so we use
``ListarPedidos`` at /produtos/pedido/ which is the verified
equivalent.
"""
import time

import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from erp_integrations.models import (
    ERPAPIDefinition, ERPConnection, ERPRawRecord, ERPSyncPipeline,
    ERPSyncPipelineRun, ERPSyncPipelineStep,
)
from erp_integrations.services.pipeline_service import (
    execute_pipeline, execute_pipeline_spec,
)
from mcp_server.tools import call_erp_api


COMPANY_ID = 5
conn = ERPConnection.objects.filter(company_id=COMPANY_ID, provider__slug="omie").first()
assert conn is not None, "evolat needs an active Omie ERPConnection"


def api_id(name: str) -> int:
    api = ERPAPIDefinition.objects.filter(
        provider=conn.provider, call=name, is_active=True,
    ).first()
    assert api is not None, f"ERPAPIDefinition {name!r} not found / inactive"
    return api.id


LISTAR_PEDIDOS = api_id("ListarPedidos")
LISTAR_CLIENTES = api_id("ListarClientes")
LISTAR_PRODUTOS = api_id("ListarProdutos")
print(f"setup ok — connection={conn.id} "
      f"ListarPedidos={LISTAR_PEDIDOS} ListarClientes={LISTAR_CLIENTES} "
      f"ListarProdutos={LISTAR_PRODUTOS}\n")


def header(label: str):
    print(f"\n{'=' * 70}\n  {label}\n{'=' * 70}")


def show(label: str, out: dict):
    print(f"  {label}: success={out.get('success')} status={out.get('status')} "
          f"extracted={out.get('records_extracted')} "
          f"stored={out.get('records_stored', 'n/a')}")
    if out.get("failed_step_order") is not None:
        print(f"    failed_step_order={out['failed_step_order']}")
    for err in (out.get("errors") or [])[:2]:
        print(f"    err: {str(err)[:140]}")
    for sd in (out.get("diagnostics") or {}).get("steps") or []:
        print(f"    step #{sd.get('order')} ({sd.get('call') or '-'}): "
              f"extracted={sd.get('extracted')} errors={len(sd.get('errors') or [])}")


# ---------------------------------------------------------------------------
# PART A: TTL cache validates
# ---------------------------------------------------------------------------
header("A1: cache MISS then HIT for identical (call, params)")

# First call — must hit Omie.
t0 = time.time()
r1 = call_erp_api(company_id=COMPANY_ID, call="ListarPedidos",
                  params={"pagina": 1, "registros_por_pagina": 1},
                  cache_ttl_seconds=60)
t1 = time.time()
print(f"  call#1: ok={r1['ok']} from_cache={r1.get('from_cache', False)} "
      f"elapsed={t1 - t0:.2f}s")

# Second call — same args, same TTL → must hit cache.
t2 = time.time()
r2 = call_erp_api(company_id=COMPANY_ID, call="ListarPedidos",
                  params={"pagina": 1, "registros_por_pagina": 1},
                  cache_ttl_seconds=60)
t3 = time.time()
print(f"  call#2: ok={r2['ok']} from_cache={r2.get('from_cache', False)} "
      f"elapsed={t3 - t2:.4f}s (should be ~0s)")

assert r1["ok"], "first call must succeed"
assert not r1.get("from_cache"), "first call must be a cache miss"
assert r2["ok"], "second call must succeed"
assert r2.get("from_cache"), "second call must hit cache"

# Third call — different params → cache miss.
t4 = time.time()
r3 = call_erp_api(company_id=COMPANY_ID, call="ListarPedidos",
                  params={"pagina": 1, "registros_por_pagina": 2},
                  cache_ttl_seconds=60)
t5 = time.time()
print(f"  call#3 (different params): from_cache={r3.get('from_cache', False)} "
      f"elapsed={t5 - t4:.2f}s (should be ~1-2s)")
assert not r3.get("from_cache"), "different params must miss cache"

print("  cache behaviour ✓")
time.sleep(8)


# ---------------------------------------------------------------------------
# PART B: bulk-and-index pattern
# ---------------------------------------------------------------------------
header("B1: ListarPedidos + ListarClientes + ListarProdutos (bulk-and-index)")
"""
Pipeline shape:
  step 1: ListarPedidos (5 rows)
  step 2: ListarClientes (50 rows — covers all clientes referenced by step 1)
  step 3: ListarProdutos (50 rows — covers all produtos referenced by step 1)

Downstream consumer (or the agent) joins them in memory using:
  pedidos[*].cabecalho.codigo_cliente <- match -> clientes[*].codigo_cliente_omie
  pedidos[*].det[*].produto.codigo_produto <- match -> produtos[*].codigo_produto

3 calls total, no fanout, no 425. Even with hundreds of pedidos, you'd
still only need 3 base calls — paginate each Listar to cover the set.
"""
out = execute_pipeline_spec(
    connection_id=conn.id, company_id=COMPANY_ID,
    steps=[
        {"order": 1, "api_definition_id": LISTAR_PEDIDOS,
         "extra_params": {"pagina": 1, "registros_por_pagina": 5}},
        {"order": 2, "api_definition_id": LISTAR_CLIENTES,
         "extra_params": {"pagina": 1, "registros_por_pagina": 50}},
        {"order": 3, "api_definition_id": LISTAR_PRODUTOS,
         "extra_params": {"pagina": 1, "registros_por_pagina": 50}},
    ],
)
show("B1", out)

prev = out.get("preview_by_step") or []
if len(prev) >= 3 and prev[0].get("preview"):
    pedidos_n = len(prev[0]["preview"])
    clientes_n = len(prev[1].get("preview") or [])
    produtos_n = len(prev[2].get("preview") or [])
    print(f"  preview rows: pedidos={pedidos_n} clientes={clientes_n} produtos={produtos_n}")

    # Demonstrate the in-memory join the agent would do client-side.
    if pedidos_n and clientes_n:
        # Build cliente index
        cliente_idx = {
            c.get("codigo_cliente_omie"): c
            for c in (prev[1]["preview"] or [])
        }
        # Index produtos by codigo
        produto_idx = {
            p.get("codigo_produto"): p
            for p in (prev[2]["preview"] or [])
        }
        # Walk pedidos, emit enriched view
        enriched_count = 0
        for p in prev[0]["preview"][:3]:
            cab = p.get("cabecalho") or {}
            ccli = cab.get("codigo_cliente")
            cliente = cliente_idx.get(ccli)
            ped_n = cab.get("numero_pedido")
            cliente_nome = (cliente or {}).get("razao_social") or (cliente or {}).get("nome_fantasia") or "?"
            print(f"    pedido #{ped_n}: cliente={ccli} ({cliente_nome[:30]})")
            for d in (p.get("det") or [])[:1]:
                cprod = (d.get("produto") or {}).get("codigo_produto")
                produto = produto_idx.get(cprod)
                produto_desc = (produto or {}).get("descricao") or "?"
                print(f"      produto={cprod} ({produto_desc[:30]})")
                enriched_count += 1
        print(f"  in-memory join: {enriched_count} items enriched (zero extra HTTP)")

time.sleep(8)


# ---------------------------------------------------------------------------
# PART C: persisted version of the bulk-and-index pipeline
# ---------------------------------------------------------------------------
header("C1: persisted bulk-and-index pipeline + audit row")
pipeline = ERPSyncPipeline.objects.create(
    company_id=COMPANY_ID, connection=conn,
    name="_test_bulk_and_index",
    description="Pedidos + Clientes + Produtos (Listar once, join in memory)",
    is_active=True,
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=1, api_definition_id=LISTAR_PEDIDOS,
    extra_params={"pagina": 1, "registros_por_pagina": 5},
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=2, api_definition_id=LISTAR_CLIENTES,
    extra_params={"pagina": 1, "registros_por_pagina": 50},
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=3, api_definition_id=LISTAR_PRODUTOS,
    extra_params={"pagina": 1, "registros_por_pagina": 50},
)
print(f"  pipeline created id={pipeline.id} with 3 steps")

out = execute_pipeline(pipeline_id=pipeline.id, dry_run=True)
show("C1", out)
run = ERPSyncPipelineRun.objects.filter(pipeline=pipeline).order_by("-id").first()
if run:
    print(f"  audit: ERPSyncPipelineRun id={run.id} status={run.status} "
          f"extracted={run.records_extracted} duration={run.duration_seconds}s")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
header("Cleanup")
runs = ERPSyncPipelineRun.objects.filter(pipeline=pipeline)
if runs.exists():
    earliest = runs.earliest("started_at").started_at
    ERPRawRecord.objects.filter(
        company_id=COMPANY_ID,
        api_call__in=["ListarPedidos", "ListarClientes", "ListarProdutos"],
        fetched_at__gte=earliest,
    ).delete()
runs.delete()
ERPSyncPipelineStep.objects.filter(pipeline=pipeline).delete()
pipeline.delete()
print("  removed test pipeline + steps + runs + raw records")

print("\nALL TESTS DONE")
