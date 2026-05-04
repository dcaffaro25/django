"""End-to-end validation of the ERP sync pipeline using ListarPedidos
as the base call, enriched with ConsultarCliente / ConsultarProduto.

Originally meant to use ``ConsultarPedidoVenda`` (per the user request),
but live probing revealed that method does not exist on the Omie API
(``Method "ConsultarPedidoVenda" not exists``). The closest verified
equivalent for "list of pedidos with cabecalho + items" is
``ListarPedidos`` at ``/api/v1/produtos/pedido/`` — same shape, same
codigo_cliente / codigo_produto fields available for enrichment.

Test matrix — designed for a single end-to-end pass without thrashing
Omie's per-call+params throttle (425 Too Early), which fires when the
same call+params is fired in rapid succession from the same app_key:

  T1 — sandbox, single step (ListarPedidos)
       → validates execute_pipeline_spec basic dispatch
  T2 — sandbox, three steps with fanout (Pedidos → Cliente → Produto)
       → validates JMESPath fanout + nested fanout
  T3 — persisted pipeline (ERPSyncPipeline + Steps + Run), dry_run=True
       → validates execute_pipeline + ERPSyncPipelineRun audit
  T4 — error path: unknown api_definition_id → clean error blob
  T5 — error path: invalid JMESPath → clean error captured in run

We deliberately don't run the same test twice — it would hit the 425
throttle on the second call with identical params. Production agents
call once per user prompt and don't normally cascade.
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


COMPANY_ID = 5
conn = ERPConnection.objects.filter(company_id=COMPANY_ID, provider__slug="omie").first()
assert conn is not None, "evolat needs an active Omie ERPConnection"


def api_id(call_name: str) -> int:
    api = ERPAPIDefinition.objects.filter(
        provider=conn.provider, call=call_name, is_active=True,
    ).first()
    assert api is not None, f"ERPAPIDefinition {call_name!r} not found or inactive"
    return api.id


LISTAR_PEDIDOS_ID = api_id("ListarPedidos")
CONSULTAR_CLIENTE_ID = api_id("ConsultarCliente")
CONSULTAR_PRODUTO_ID = api_id("ConsultarProduto")
print(f"Setup OK: connection={conn.id}, ListarPedidos={LISTAR_PEDIDOS_ID}, "
      f"ConsultarCliente={CONSULTAR_CLIENTE_ID}, ConsultarProduto={CONSULTAR_PRODUTO_ID}\n")


def header(label: str):
    print(f"\n{'=' * 70}\n  {label}\n{'=' * 70}")


def show(label: str, out: dict):
    print(f"  {label}: success={out.get('success')} status={out.get('status')} "
          f"extracted={out.get('records_extracted')} "
          f"stored={out.get('records_stored', 'n/a')}")
    if out.get("failed_step_order") is not None:
        print(f"    failed_step_order={out['failed_step_order']}")
    for err in (out.get("errors") or [])[:3]:
        print(f"    err: {str(err)[:160]}")
    for sd in (out.get("diagnostics") or {}).get("steps") or []:
        print(f"    step #{sd.get('order')} ({sd.get('call') or '-'}): "
              f"extracted={sd.get('extracted')} errors={len(sd.get('errors') or [])}")


# ---------------------------------------------------------------------------
# T1: sandbox single step
# ---------------------------------------------------------------------------
header("T1: ListarPedidos sandbox (single step)")
out = execute_pipeline_spec(
    connection_id=conn.id, company_id=COMPANY_ID,
    steps=[{
        "order": 1, "api_definition_id": LISTAR_PEDIDOS_ID,
        "extra_params": {"pagina": 1, "registros_por_pagina": 1},
    }],
)
show("T1", out)
prev = (out.get("preview_by_step") or [{}])[0].get("preview") or []
if prev:
    cab = prev[0].get("cabecalho") or {}
    print(f"  pedido sample: codigo_pedido={cab.get('codigo_pedido')} "
          f"codigo_cliente={cab.get('codigo_cliente')} items={len(prev[0].get('det') or [])}")

print("\nThrottle pause (10s) — avoid 425 from cascading same-params calls")
time.sleep(10)


# ---------------------------------------------------------------------------
# T2: three-step sandbox with nested fanout
# ---------------------------------------------------------------------------
header("T2: Pedidos -> Cliente -> Produto (nested fanout, sandbox)")
out = execute_pipeline_spec(
    connection_id=conn.id, company_id=COMPANY_ID,
    steps=[
        {"order": 1, "api_definition_id": LISTAR_PEDIDOS_ID,
         "extra_params": {"pagina": 1, "registros_por_pagina": 1}},
        {"order": 2, "api_definition_id": CONSULTAR_CLIENTE_ID,
         "param_bindings": [{
             "mode": "fanout", "source_step": 1,
             "expression": "pedido_venda_produto[*].cabecalho.codigo_cliente",
             "into": "codigo_cliente_omie",
         }]},
        {"order": 3, "api_definition_id": CONSULTAR_PRODUTO_ID,
         "param_bindings": [{
             "mode": "fanout", "source_step": 1,
             "expression": "pedido_venda_produto[*].det[*].produto.codigo_produto[]",
             "into": "codigo_produto",
         }]},
    ],
)
show("T2", out)

print("\nThrottle pause (10s)")
time.sleep(10)


# ---------------------------------------------------------------------------
# T3: persisted pipeline, dry_run=True
# ---------------------------------------------------------------------------
header("T3: persisted pipeline, dry_run=True (audit row)")
pipeline = ERPSyncPipeline.objects.create(
    company_id=COMPANY_ID, connection=conn,
    name="_test_pedidos_enriched",
    description="Validation pipeline: Pedidos -> Cliente -> Produto",
    is_active=True,
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=1, api_definition_id=LISTAR_PEDIDOS_ID,
    extra_params={"pagina": 1, "registros_por_pagina": 1},
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=2, api_definition_id=CONSULTAR_CLIENTE_ID,
    param_bindings=[{
        "mode": "fanout", "source_step": 1,
        "expression": "pedido_venda_produto[*].cabecalho.codigo_cliente",
        "into": "codigo_cliente_omie",
    }],
)
ERPSyncPipelineStep.objects.create(
    pipeline=pipeline, order=3, api_definition_id=CONSULTAR_PRODUTO_ID,
    param_bindings=[{
        "mode": "fanout", "source_step": 1,
        "expression": "pedido_venda_produto[*].det[*].produto.codigo_produto[]",
        "into": "codigo_produto",
    }],
)
print(f"  pipeline created: id={pipeline.id}, 3 steps")

out = execute_pipeline(pipeline_id=pipeline.id, dry_run=True)
show("T3", out)
run_t3 = ERPSyncPipelineRun.objects.filter(pipeline=pipeline).order_by("-id").first()
if run_t3:
    print(f"  audit row: ERPSyncPipelineRun id={run_t3.id} status={run_t3.status} "
          f"extracted={run_t3.records_extracted} duration={run_t3.duration_seconds}s")


# ---------------------------------------------------------------------------
# T4: error path — unknown api_definition_id
# ---------------------------------------------------------------------------
header("T4: error path — unknown api_definition_id")
out = execute_pipeline_spec(
    connection_id=conn.id, company_id=COMPANY_ID,
    steps=[{"order": 1, "api_definition_id": 9_999_999}],
)
print(f"  T4 success={out.get('success')} error={(out.get('error') or '')[:140]}")


# ---------------------------------------------------------------------------
# T5: error path — invalid JMESPath in fanout binding
# ---------------------------------------------------------------------------
header("T5: error path — invalid JMESPath")
out = execute_pipeline_spec(
    connection_id=conn.id, company_id=COMPANY_ID,
    steps=[
        {"order": 1, "api_definition_id": LISTAR_PEDIDOS_ID,
         "extra_params": {"pagina": 1, "registros_por_pagina": 1}},
        {"order": 2, "api_definition_id": CONSULTAR_CLIENTE_ID,
         "param_bindings": [{
             "mode": "fanout", "source_step": 1,
             "expression": "$$$invalid",
             "into": "codigo_cliente_omie",
         }]},
    ],
)
print(f"  T5 success={out.get('success')} status={out.get('status')} "
      f"failed_step={out.get('failed_step_order')}")
for err in (out.get("errors") or [])[:3]:
    print(f"    err: {str(err)[:160]}")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
header("Cleanup")
runs = ERPSyncPipelineRun.objects.filter(pipeline=pipeline)
if runs.exists():
    earliest = runs.earliest("started_at").started_at
    ERPRawRecord.objects.filter(
        company_id=COMPANY_ID,
        api_call__in=["ListarPedidos", "ConsultarCliente", "ConsultarProduto"],
        fetched_at__gte=earliest,
    ).delete()
runs.delete()
ERPSyncPipelineStep.objects.filter(pipeline=pipeline).delete()
pipeline.delete()
print("  removed test pipeline + steps + runs + raw records")

print("\nALL TESTS DONE")
