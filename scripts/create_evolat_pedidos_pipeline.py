"""Create / refresh two production pipelines for evolat. Both follow the
bulk-and-index idiom: each step is a Listar* call that pulls a whole
dataset in one shot, downstream consumers join in memory by codigo_*
foreign keys. No fanout, no per-row throttle.

  evolat_omie_pedidos_full
    step 1 — ListarPedidos      (vendas / orders header + items)
    step 2 — ListarClientes     (join: pedidos[*].cabecalho.codigo_cliente)
    step 3 — ListarProdutos     (join: pedidos[*].det[*].produto.codigo_produto)

  evolat_omie_movimentos_full
    step 1 — ListarMovimentos   (financial movements / extrato consolidado)
    step 2 — ListarContasReceber (join: movimentos[*].codigo_lancamento for "R")
    step 3 — ListarContasPagar  (join: movimentos[*].codigo_lancamento for "P")
    step 4 — ListarCategorias   (join: lançamentos[*].codigo_categoria)

Idempotent: re-running updates step orderings + parameters in place,
no duplicates.

Usage:
    python manage.py shell < scripts/create_evolat_pedidos_pipeline.py
"""
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")
django.setup()

from erp_integrations.models import (
    ERPAPIDefinition, ERPConnection, ERPSyncPipeline, ERPSyncPipelineStep,
)


COMPANY_ID = 5
conn = ERPConnection.objects.filter(
    company_id=COMPANY_ID, provider__slug="omie", is_active=True,
).first()
assert conn is not None, "No active Omie ERPConnection for company 5 (evolat)"


def api_id(name: str) -> int:
    api = ERPAPIDefinition.objects.filter(
        provider=conn.provider, call=name, is_active=True,
    ).first()
    assert api is not None, (
        f"ERPAPIDefinition {name!r} not found / inactive — "
        f"run seed_omie_api_full first"
    )
    return api.id


def upsert_pipeline(name: str, description: str, steps: list[dict]) -> ERPSyncPipeline:
    """Create or refresh a pipeline + its steps idempotently."""
    pipeline, created = ERPSyncPipeline.objects.update_or_create(
        company_id=COMPANY_ID, connection=conn, name=name,
        defaults={"description": description, "is_active": True},
    )
    print(("created" if created else "updated"), f"pipeline id={pipeline.id} ({name})")

    # Reset steps — easier than diffing.
    ERPSyncPipelineStep.objects.filter(pipeline=pipeline).delete()
    for spec in steps:
        ERPSyncPipelineStep.objects.create(
            pipeline=pipeline,
            order=spec["order"],
            api_definition_id=api_id(spec["call"]),
            extra_params=spec.get("extra_params") or {},
            param_bindings=spec.get("param_bindings") or [],
        )
        print(f"  + step {spec['order']}: {spec['call']} {spec.get('extra_params') or {}}")
    return pipeline


# ---------------------------------------------------------------------------
# Pipeline 1: pedidos full snapshot
# ---------------------------------------------------------------------------
upsert_pipeline(
    name="evolat_omie_pedidos_full",
    description=(
        "Bulk-and-index Omie pull for evolat — sales side. "
        "Pedidos + Clientes + Produtos. Downstream joins by "
        "codigo_cliente / codigo_produto. No fanout, no 425 throttle."
    ),
    steps=[
        {"order": 1, "call": "ListarPedidos",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
        {"order": 2, "call": "ListarClientes",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
        {"order": 3, "call": "ListarProdutos",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
    ],
)


# ---------------------------------------------------------------------------
# Pipeline 2: movimentos full snapshot
# ---------------------------------------------------------------------------
# Note: ListarMovimentos uses the CamelCase pagination convention
# (nPagina/nRegPorPagina) per Omie's per-endpoint complex type. The
# other Listar* calls in this pipeline use snake_case as usual — the
# seeded param_schema enforces this per call.
upsert_pipeline(
    name="evolat_omie_movimentos_full",
    description=(
        "Bulk-and-index Omie pull for evolat — financial side. "
        "Movimentos + ContasReceber + ContasPagar + Categorias. "
        "Downstream joins by codigo_lancamento_omie / codigo_categoria. "
        "No fanout, no 425 throttle."
    ),
    steps=[
        {"order": 1, "call": "ListarMovimentos",
         "extra_params": {"nPagina": 1, "nRegPorPagina": 100}},
        {"order": 2, "call": "ListarContasReceber",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
        {"order": 3, "call": "ListarContasPagar",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
        {"order": 4, "call": "ListarCategorias",
         "extra_params": {"pagina": 1, "registros_por_pagina": 100}},
    ],
)


# ---------------------------------------------------------------------------
# Tear down the older combined pipeline if it lingers from a prior run
# ---------------------------------------------------------------------------
old = ERPSyncPipeline.objects.filter(
    company_id=COMPANY_ID, name__in=["evolat_omie_pedidos_full__combined", "evolat_omie_full"],
)
for p in old:
    print(f"removing legacy pipeline id={p.id} ({p.name})")
    p.delete()


print("\nReady. Run either pipeline with:")
print("  from erp_integrations.services.pipeline_service import execute_pipeline")
print("  execute_pipeline(pipeline_id=<id>, dry_run=True)")
