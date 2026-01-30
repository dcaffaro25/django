# erp_integrations/erp_etl.py
"""
ETL from ERP API JSON response to app models (same commit flow as Excel ETL).

- Transforms API response list (e.g. produto_servico_cadastro) into sheet/row format
  expected by multitenancy.tasks.execute_import_job.
- Optional: emit ProductServiceCategory rows from unique category keys, then ProductService
  rows with category_fk tokens.
- Supports field_mappings (API key -> model field), default_values, and dot-notation
  for nested keys (e.g. dadosIbpt.aliqFederal).

Usage (like Excel ETL commit):
  1. Create an ErpApiEtlMapping in Admin (or use OMIE_PRODUTOS_CADASTRO_MAPPING as reference).
  2. Fetch Omie response (e.g. ListarProdutos -> response with produto_servico_cadastro).
  3. Preview: execute_erp_etl_import(company_id, response_payload, mapping_id, commit=False).
  4. Commit: execute_erp_etl_import(company_id, response_payload, mapping_id, commit=True).

  Or POST to /api/{tenant_id}/erp/etl-import/ with body:
  {"mapping_id": 1, "response": { "produto_servico_cadastro": [...] }, "commit": false}.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db import transaction

logger = logging.getLogger(__name__)


# Default mapping for Omie ListarProdutos response (produto_servico_cadastro -> ProductService)
OMIE_PRODUTOS_CADASTRO_MAPPING = {
    "response_list_key": "produto_servico_cadastro",
    "target_model": "ProductService",
    "field_mappings": {
        "codigo": "code",
        "descricao": "name",
        "valor_unitario": "price",
        "descr_detalhada": "description",
        "ncm": "tax_code",
        "inativo": "is_active",
        "quantidade_estoque": "stock_quantity",
    },
    "row_id_api_key": "codigo",
    "default_values": {
        "item_type": "product",
        "price": 0,
        "cost": None,
        "track_inventory": False,
        "stock_quantity": 0,
    },
    "category_from_same_response": True,
    "category_name_key": "descricao_familia",
    "category_id_key": "codigo_familia",
    "category_target_model": "ProductServiceCategory",
    "category_fk_field": "category_fk",
}


def _get_nested(data: dict, key: str) -> Any:
    """Get value by key; supports dot notation for nested keys (e.g. dadosIbpt.aliqFederal)."""
    if not key or "." not in key:
        return data.get(key)
    parts = key.split(".", 1)
    head, tail = parts[0], parts[1]
    val = data.get(head)
    if val is None or not isinstance(val, dict):
        return None
    return _get_nested(val, tail)


def _coerce_value(value: Any, for_decimal: bool = False, for_is_active_from_inativo: bool = False) -> Any:
    """Coerce API values for our models (e.g. 'N'/'S' -> bool, numeric strings -> Decimal)."""
    if value is None:
        return None
    # Omie inativo: N = active (True), S = inactive (False)
    if for_is_active_from_inativo and isinstance(value, str) and value.strip().upper() in ("S", "N"):
        return value.strip().upper() == "N"
    if isinstance(value, str) and value.strip().upper() in ("S", "N", "Y", "YES", "NO") and not for_is_active_from_inativo:
        return value.strip().upper() in ("S", "Y", "YES")
    if for_decimal and value is not None:
        try:
            if isinstance(value, (int, float)):
                return Decimal(str(value))
            if isinstance(value, str):
                return Decimal(value.replace(",", ".").strip())
        except Exception:
            pass
    return value


def _build_row_from_item(
    item: dict,
    field_mappings: Dict[str, str],
    default_values: Dict[str, Any],
    row_id_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build one row (model-field keys) from one API item.
    field_mappings: API key -> model field name.
    default_values: merged after mapped values.
    row_id_key: if set, use this API key's value as __row_id (overrides mapping for __row_id).
    """
    row: Dict[str, Any] = {}
    for api_key, model_field in field_mappings.items():
        val = _get_nested(item, api_key)
        if val is None and model_field in default_values:
            val = default_values.get(model_field)
        if val is not None and model_field != "__row_id":
            if model_field in ("price", "cost", "stock_quantity") or "amount" in model_field:
                val = _coerce_value(val, for_decimal=True)
            elif model_field == "is_active" and api_key == "inativo":
                val = _coerce_value(val, for_is_active_from_inativo=True)
            elif model_field in ("is_active", "track_inventory"):
                val = _coerce_value(val)
            row[model_field] = val
    if row_id_key:
        rid = _get_nested(item, row_id_key)
        if rid is not None:
            row["__row_id"] = str(rid).strip()
    elif "__row_id" in row:
        pass  # already set by mapping
    for k, v in default_values.items():
        if k not in row:
            row[k] = v
    return row


def transform_erp_response_to_sheets(
    company_id: int,
    response_payload: dict,
    mapping: Any,
) -> List[Dict[str, Any]]:
    """
    Transform ERP API response into list of sheets for execute_import_job.

    Sheets format: [{"model": "ProductServiceCategory", "rows": [...], "sheet_name": "..."}, ...]
    Category sheet is emitted first when category_from_same_response is True.
    """
    if not mapping.is_active:
        return []

    list_key = mapping.response_list_key
    items = response_payload.get(list_key)
    if not isinstance(items, list):
        logger.warning("ERP ETL: response key %r missing or not a list", list_key)
        return []

    sheets: List[Dict[str, Any]] = []
    default_values = dict(mapping.default_values or {})
    # execute_import_job attaches company_id via _attach_company_context when company_fk is absent

    # Optional: category sheet from unique category_id_key + category_name_key
    if mapping.category_from_same_response and mapping.category_id_key and mapping.category_name_key:
        seen: Dict[Any, str] = {}
        category_rows: List[Dict[str, Any]] = []
        for item in items:
            cid = _get_nested(item, mapping.category_id_key)
            cname = _get_nested(item, mapping.category_name_key)
            if cid is None and cname is None:
                continue
            key = (cid, (cname or "").strip())
            if key in seen:
                continue
            token = f"fam_{cid}" if cid is not None else f"fam_{hash(cname) % 10**10}"
            seen[key] = token
            category_rows.append({
                "__row_id": token,
                "name": (cname or str(cid) or "").strip() or token,
            })
        if category_rows:
            sheets.append({
                "model": mapping.category_target_model or "ProductServiceCategory",
                "rows": category_rows,
                "sheet_name": f"erp_etl_{mapping.response_list_key}_categories",
            })

    # Main sheet: target_model rows
    row_id_key = getattr(mapping, "row_id_api_key", None) or None
    if not row_id_key:
        for api_key, model_field in (mapping.field_mappings or {}).items():
            if model_field == "__row_id":
                row_id_key = api_key
                break
    rows: List[Dict[str, Any]] = []
    for item in items:
        row = _build_row_from_item(
            item,
            mapping.field_mappings or {},
            default_values,
            row_id_key=row_id_key,
        )
        if not row:
            continue
        # Point category_fk to category token when we emitted categories
        if mapping.category_from_same_response and mapping.category_fk_field and mapping.category_id_key:
            cid = _get_nested(item, mapping.category_id_key)
            if cid is not None:
                row[mapping.category_fk_field] = f"fam_{cid}"
        rows.append(row)

    sheets.append({
        "model": mapping.target_model,
        "rows": rows,
        "sheet_name": f"erp_etl_{mapping.response_list_key}",
    })
    return sheets


def execute_erp_etl_import(
    company_id: int,
    response_payload: dict,
    mapping_id: int,
    commit: bool = False,
    import_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run ETL: transform ERP response with given mapping, then execute_import_job (preview or commit).

    Same contract as Excel ETL: commit=False previews, commit=True writes to DB.
    """
    from multitenancy.tasks import execute_import_job

    from .models import ErpApiEtlMapping

    mapping = ErpApiEtlMapping.objects.filter(company_id=company_id, id=mapping_id).first()
    if not mapping:
        return {
            "success": False,
            "errors": [f"ErpApiEtlMapping id={mapping_id} not found for company_id={company_id}"],
            "outputs_by_model": {},
        }

    sheets = transform_erp_response_to_sheets(company_id, response_payload, mapping)
    if not sheets:
        return {
            "success": False,
            "errors": ["No sheets produced (empty list or mapping inactive)."],
            "outputs_by_model": {},
        }

    meta = import_metadata or {}
    meta.setdefault("source", "ERP API ETL")
    meta.setdefault("function", "execute_erp_etl_import")
    meta.setdefault("mapping_id", mapping_id)
    meta.setdefault("response_list_key", mapping.response_list_key)

    return execute_import_job(
        company_id=company_id,
        sheets=sheets,
        commit=commit,
        import_metadata=meta,
    )
