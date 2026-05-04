"""Read-side service for the PedidoVendas report.

Reads the latest ``ERPRawRecord`` rows produced by the
``evolat_omie_pedidos_full`` pipeline (or any pipeline that pulls
ListarPedidos / ListarClientes / ListarProdutos), joins them in
memory by codigo_* foreign keys, and returns an enriched view.

No HTTP. The pipeline does the fetching; this service reads the
"temp DB" snapshot.

Two reasons we read from ``ERPRawRecord`` rather than the
domain-mapped tables:

* The ETL into ``billing.Invoice`` etc. is per-tenant configurable
  and may not be wired for every customer. The raw layer is always
  available right after a pipeline run.
* Reports want to surface what's currently in Omie, not what's been
  imported into Sysnord. The raw snapshot is the source of truth
  for that.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date as _date
from decimal import Decimal
from typing import Any

from django.db.models import Max

from erp_integrations.models import (
    ERPRawRecord,
    ERPSyncPipeline,
    ERPSyncPipelineRun,
)


def _safe_decimal(value: Any) -> Decimal:
    if value in (None, "", "None"):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _parse_date_br(value: Any) -> str | None:
    """Convert Omie's dd/mm/aaaa to ISO YYYY-MM-DD."""
    if not value or not isinstance(value, str):
        return None
    parts = value.split("/")
    if len(parts) != 3:
        return value  # already ISO?
    d, m, y = parts
    return f"{y}-{m}-{d}"


def _latest_records(company_id: int, api_call: str) -> list[ERPRawRecord]:
    """Pull the most-recent record per external_id for a given call.

    With ``unique_id_config.on_duplicate=update`` the upsert path
    keeps one row per external_id and refreshes ``fetched_at``. So a
    simple "all rows for this call" query already returns the latest
    snapshot — no group-by needed. Fallback for legacy calls without
    unique_id_config: collapse by external_id picking the freshest.
    """
    qs = ERPRawRecord.objects.filter(company_id=company_id, api_call=api_call)
    rows = list(qs.order_by("external_id", "-fetched_at"))
    seen: dict[str | None, ERPRawRecord] = {}
    for row in rows:
        key = row.external_id
        # Without an external_id we can't dedupe — keep all such rows.
        if key is None:
            seen[id(row)] = row
        elif key not in seen:
            seen[key] = row
    return list(seen.values())


def _build_index(rows: list[ERPRawRecord], key_path: str) -> dict[Any, dict]:
    """Index records by a JMESPath-style dotted key. Simple-and-fast."""
    out: dict[Any, dict] = {}
    for row in rows:
        data = row.data or {}
        value: Any = data
        for part in key_path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = None
                break
        if value is not None:
            out[value] = data
    return out


def get_pedido_report(
    *,
    company_id: int,
    date_from: _date | None = None,
    date_to: _date | None = None,
    etapa: str | None = None,
    codigo_cliente: int | None = None,
    search: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Build the enriched PedidoVendas report.

    Returns a dict with:

    * ``rows`` — enriched pedidos: header + cliente snippet + items
      with produto name resolved.
    * ``summary`` — KPI counts/sums.
    * ``meta`` — last pipeline run info (started_at, status,
      records_extracted) for the report's "data freshness" hint.
    * ``filters_applied`` — echoes what was used to filter.

    All numeric totals are stringified Decimal.
    """
    pedido_rows = _latest_records(company_id, "ListarPedidos")
    cliente_rows = _latest_records(company_id, "ListarClientes")
    produto_rows = _latest_records(company_id, "ListarProdutos")

    cliente_idx = _build_index(cliente_rows, "codigo_cliente_omie")
    produto_idx = _build_index(produto_rows, "codigo_produto")

    enriched: list[dict[str, Any]] = []
    for row in pedido_rows:
        ped = row.data or {}
        cab = ped.get("cabecalho") or {}
        total_pedido = ped.get("total_pedido") or {}
        info = ped.get("infoCadastro") or {}

        codigo_cli = cab.get("codigo_cliente")
        cliente = cliente_idx.get(codigo_cli) or {}

        items: list[dict[str, Any]] = []
        for det in (ped.get("det") or []):
            prod = det.get("produto") or {}
            ide = det.get("ide") or {}
            cprod = prod.get("codigo_produto")
            full_prod = produto_idx.get(cprod) or {}
            items.append({
                "codigo_produto": cprod,
                "codigo_item_integracao": ide.get("codigo_item_integracao"),
                "ncm": prod.get("ncm"),
                "cfop": prod.get("cfop"),
                "descricao": prod.get("descricao") or full_prod.get("descricao"),
                "valor_unitario": str(_safe_decimal(prod.get("valor_unitario"))),
                "quantidade": str(_safe_decimal(prod.get("quantidade"))),
                "valor_total": str(_safe_decimal(prod.get("valor_total"))),
                "produto_resolved_name": full_prod.get("descricao"),
                "produto_unit": full_prod.get("unidade"),
            })

        codigo_pedido = cab.get("codigo_pedido")
        numero_pedido = cab.get("numero_pedido")
        etapa_pedido = cab.get("etapa")

        valor_total = _safe_decimal(total_pedido.get("valor_total_pedido"))
        date_iso = _parse_date_br(info.get("dInc"))

        enriched.append({
            "codigo_pedido": codigo_pedido,
            "numero_pedido": numero_pedido,
            "etapa": etapa_pedido,
            "data_inclusao": date_iso,
            "data_inclusao_raw": info.get("dInc"),
            "valor_total_pedido": str(valor_total),
            "qtde_itens": cab.get("quantidade_itens") or len(items),
            "encerrado": cab.get("encerrado"),
            "bloqueado": cab.get("bloqueado"),
            "cliente": {
                "codigo_cliente_omie": codigo_cli,
                "razao_social": cliente.get("razao_social"),
                "nome_fantasia": cliente.get("nome_fantasia"),
                "cnpj_cpf": cliente.get("cnpj_cpf"),
                "uf": (cliente.get("endereco") or {}).get("estado"),
                "city": (cliente.get("endereco") or {}).get("cidade"),
            },
            "items": items,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
            "_etapa_lower": (etapa_pedido or "").lower(),
        })

    # Apply filters in-memory.
    def _within_dates(d: dict[str, Any]) -> bool:
        iso = d.get("data_inclusao")
        if not iso:
            return True
        try:
            dt = _date.fromisoformat(iso)
        except ValueError:
            return True
        if date_from and dt < date_from:
            return False
        if date_to and dt > date_to:
            return False
        return True

    def _matches(d: dict[str, Any]) -> bool:
        if not _within_dates(d):
            return False
        if etapa and d.get("etapa") != etapa:
            return False
        if codigo_cliente and d.get("cliente", {}).get("codigo_cliente_omie") != codigo_cliente:
            return False
        if search:
            haystack_parts = [
                str(d.get("numero_pedido") or ""),
                str(d.get("codigo_pedido") or ""),
                str(d.get("cliente", {}).get("razao_social") or ""),
                str(d.get("cliente", {}).get("nome_fantasia") or ""),
                str(d.get("cliente", {}).get("cnpj_cpf") or ""),
            ]
            if search.lower() not in " ".join(haystack_parts).lower():
                return False
        return True

    filtered = [d for d in enriched if _matches(d)]
    filtered.sort(key=lambda d: d.get("data_inclusao") or "0000-00-00", reverse=True)

    # Summary KPIs across the FULL set (before limit).
    total_amount = sum((_safe_decimal(d["valor_total_pedido"]) for d in filtered), start=Decimal("0"))
    by_etapa = Counter((d.get("etapa") or "?") for d in filtered)

    # Find latest pipeline run for "freshness" hint.
    pipeline = ERPSyncPipeline.objects.filter(
        company_id=company_id, name="evolat_omie_pedidos_full",
    ).first()
    last_run = None
    if pipeline:
        last_run = (
            ERPSyncPipelineRun.objects
            .filter(pipeline=pipeline)
            .order_by("-started_at")
            .first()
        )

    return {
        "rows": [
            {k: v for k, v in d.items() if not k.startswith("_")}
            for d in filtered[:limit]
        ],
        "summary": {
            "n_pedidos_total": len(enriched),
            "n_pedidos_filtered": len(filtered),
            "n_clientes_indexed": len(cliente_idx),
            "n_produtos_indexed": len(produto_idx),
            "valor_total_filtered": str(total_amount),
            "by_etapa": dict(by_etapa.most_common()),
        },
        "meta": {
            "limit": limit,
            "pipeline_id": pipeline.id if pipeline else None,
            "pipeline_name": pipeline.name if pipeline else None,
            "last_run": {
                "id": last_run.id,
                "status": last_run.status,
                "started_at": last_run.started_at.isoformat() if last_run else None,
                "completed_at": last_run.completed_at.isoformat() if last_run and last_run.completed_at else None,
                "records_extracted": last_run.records_extracted,
                "duration_seconds": last_run.duration_seconds,
                "is_sandbox": last_run.is_sandbox,
            } if last_run else None,
        },
        "filters_applied": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "etapa": etapa,
            "codigo_cliente": codigo_cliente,
            "search": search,
        },
    }
