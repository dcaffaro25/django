"""
Filter stack compiler for reconciliation rules.

Converts a "filter stack" JSON blob (the same shape the frontend
`<FilterStackBuilder>` emits) into a Django Q object that can be
AND'd onto a BankTransaction or JournalEntry queryset.

Stack shape
-----------

    {
      "operator": "and" | "or",
      "filters": [
        {
          "column_id": "date",
          "operator": "between",
          "value": ["2026-01-01", "2026-03-31"],
          "disabled": false
        },
        ...
      ]
    }

Filters may be nested: a child entry with no `column_id` but a
nested `operator` / `filters` list is treated as a sub-group.

Any unknown column or operator is silently ignored (safer than
crashing a reconciliation run), but surfaced via `compile_stack_report`
for UI feedback.

Columns are declared per-model in `COLUMN_REGISTRY`. Each column has:
    orm_path:   dotted Django ORM path (e.g. "bank_account__entity_id")
    type:       "string" | "number" | "date" | "datetime" | "bool"
                | "fk" | "enum" | "array"
    operators:  allowed operator whitelist for that column
    enum:       (optional) allowed values for "enum" type
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Q


# ---------------------------------------------------------------------------
# Column registry
# ---------------------------------------------------------------------------

_STRING_OPS = ("eq", "neq", "contains", "icontains", "startswith", "istartswith", "in", "is_null")
_NUMBER_OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "between", "in", "is_null")
_DATE_OPS = ("eq", "neq", "gt", "gte", "lt", "lte", "between", "is_null")
_BOOL_OPS = ("eq", "is_null")
_FK_OPS = ("eq", "neq", "in", "is_null")
_ENUM_OPS = ("eq", "neq", "in")
_ARRAY_OPS = ("contains", "overlap", "len_eq", "len_gt", "len_gte", "len_lt", "len_lte", "is_empty")


BANK_TRANSACTION_COLUMNS: Dict[str, Dict[str, Any]] = {
    "id":                  {"orm_path": "id",                  "type": "number", "operators": _NUMBER_OPS, "label": "ID"},
    "date":                {"orm_path": "date",                "type": "date",   "operators": _DATE_OPS,   "label": "Data"},
    "amount":              {"orm_path": "amount",              "type": "number", "operators": _NUMBER_OPS, "label": "Valor"},
    "description":         {"orm_path": "description",         "type": "string", "operators": _STRING_OPS, "label": "Descrição"},
    "status":              {"orm_path": "status",              "type": "enum",   "operators": _ENUM_OPS,
                            "enum": ["pending", "matched", "approved", "ignored", "unmatched"], "label": "Status"},
    "reference_number":    {"orm_path": "reference_number",    "type": "string", "operators": _STRING_OPS, "label": "Nº Referência"},
    "erp_id":              {"orm_path": "erp_id",              "type": "string", "operators": _STRING_OPS, "label": "ERP ID"},
    "tag":                 {"orm_path": "tag",                 "type": "string", "operators": _STRING_OPS, "label": "Tag"},
    "cnpj":                {"orm_path": "cnpj",                "type": "string", "operators": _STRING_OPS, "label": "CNPJ"},
    "balance_validated":   {"orm_path": "balance_validated",   "type": "bool",   "operators": _BOOL_OPS,   "label": "Saldo validado"},
    "bank_account":        {"orm_path": "bank_account_id",     "type": "fk",     "operators": _FK_OPS,
                            "fk_model": "accounting.BankAccount", "label": "Conta Bancária"},
    "currency":            {"orm_path": "currency_id",         "type": "fk",     "operators": _FK_OPS,
                            "fk_model": "accounting.Currency", "label": "Moeda"},
    "entity":              {"orm_path": "bank_account__entity_id", "type": "fk", "operators": _FK_OPS,
                            "fk_model": "multitenancy.Entity", "label": "Entidade"},
    "numeros_boleto":      {"orm_path": "numeros_boleto",      "type": "array",  "operators": _ARRAY_OPS,  "label": "Boletos"},
    "reconciliation_status": {"orm_path": "reconciliations__status", "type": "enum", "operators": _ENUM_OPS,
                              "enum": ["pending", "matched", "approved", "rejected", "unmatched"], "label": "Status conciliação"},
}


JOURNAL_ENTRY_COLUMNS: Dict[str, Dict[str, Any]] = {
    "id":                     {"orm_path": "id",                     "type": "number", "operators": _NUMBER_OPS, "label": "ID"},
    "date":                   {"orm_path": "date",                   "type": "date",   "operators": _DATE_OPS,   "label": "Data"},
    "description":            {"orm_path": "description",            "type": "string", "operators": _STRING_OPS, "label": "Descrição"},
    "debit_amount":           {"orm_path": "debit_amount",           "type": "number", "operators": _NUMBER_OPS, "label": "Débito"},
    "credit_amount":          {"orm_path": "credit_amount",          "type": "number", "operators": _NUMBER_OPS, "label": "Crédito"},
    "state":                  {"orm_path": "state",                  "type": "enum",   "operators": _ENUM_OPS,
                               "enum": ["pending", "posted", "canceled"], "label": "Estado"},
    "is_cash":                {"orm_path": "is_cash",                "type": "bool",   "operators": _BOOL_OPS,   "label": "Caixa"},
    "is_reconciled":          {"orm_path": "is_reconciled",          "type": "bool",   "operators": _BOOL_OPS,   "label": "Conciliado"},
    "bank_designation_pending": {"orm_path": "bank_designation_pending", "type": "bool", "operators": _BOOL_OPS, "label": "Banco pendente"},
    "account":                {"orm_path": "account_id",             "type": "fk",     "operators": _FK_OPS,
                               "fk_model": "accounting.Account", "label": "Conta"},
    "cost_center":            {"orm_path": "cost_center_id",         "type": "fk",     "operators": _FK_OPS,
                               "fk_model": "accounting.CostCenter", "label": "Centro de custo"},
    "tag":                    {"orm_path": "tag",                    "type": "string", "operators": _STRING_OPS, "label": "Tag"},
    "erp_id":                 {"orm_path": "erp_id",                 "type": "string", "operators": _STRING_OPS, "label": "ERP ID"},
    "transaction":            {"orm_path": "transaction_id",         "type": "fk",     "operators": _FK_OPS,
                               "fk_model": "accounting.Transaction", "label": "Transação"},
    "entity":                 {"orm_path": "transaction__entity_id", "type": "fk",     "operators": _FK_OPS,
                               "fk_model": "multitenancy.Entity", "label": "Entidade"},
    "reconciliation_status":  {"orm_path": "reconciliations__status", "type": "enum",  "operators": _ENUM_OPS,
                               "enum": ["pending", "matched", "approved", "rejected", "unmatched"], "label": "Status conciliação"},
    "payment_day_delta":      {"orm_path": "payment_day_delta",      "type": "number", "operators": _NUMBER_OPS, "label": "Δ dia pagamento"},
    "amount_discrepancy":     {"orm_path": "amount_discrepancy",     "type": "number", "operators": _NUMBER_OPS, "label": "Δ valor"},
    "is_exact_match":         {"orm_path": "is_exact_match",         "type": "bool",   "operators": _BOOL_OPS,   "label": "Match exato"},
    "is_perfect_match":       {"orm_path": "is_perfect_match",       "type": "bool",   "operators": _BOOL_OPS,   "label": "Match perfeito"},
}


COLUMN_REGISTRY: Dict[str, Dict[str, Dict[str, Any]]] = {
    "bank_transaction": BANK_TRANSACTION_COLUMNS,
    "journal_entry": JOURNAL_ENTRY_COLUMNS,
}


def get_columns(kind: str) -> Dict[str, Dict[str, Any]]:
    """Returns the column registry for 'bank_transaction' or 'journal_entry'."""
    return COLUMN_REGISTRY.get(kind, {})


def describe_columns(kind: str) -> List[Dict[str, Any]]:
    """Returns a JSON-serializable description of columns, for the frontend."""
    cols = get_columns(kind)
    out = []
    for column_id, spec in cols.items():
        row = {
            "id": column_id,
            "label": spec.get("label", column_id),
            "type": spec.get("type"),
            "operators": list(spec.get("operators", ())),
        }
        if spec.get("enum"):
            row["enum"] = list(spec["enum"])
        if spec.get("fk_model"):
            row["fk_model"] = spec["fk_model"]
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def _coerce_scalar(value: Any, col_type: str) -> Any:
    """Coerce a single scalar value to the right python type for the column."""
    if value is None:
        return None
    if col_type in ("number",):
        try:
            if isinstance(value, (int, float, Decimal)):
                return value
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
    if col_type == "fk":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if col_type == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "y", "t"):
            return True
        if s in ("0", "false", "no", "n", "f"):
            return False
        return None
    if col_type == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
    if col_type == "datetime":
        if isinstance(value, datetime):
            return value
        try:
            # accept ISO 8601
            s = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None
    # string / enum / array: return as-is (string-ish)
    return value


def _coerce_value(value: Any, col_type: str, operator: str) -> Any:
    """Coerce the entire value (scalar, list, or pair) for the given operator."""
    if operator in ("in", "overlap"):
        if not isinstance(value, (list, tuple)):
            value = [value]
        return [_coerce_scalar(v, col_type) for v in value if v is not None]
    if operator == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return None
        lo = _coerce_scalar(value[0], col_type)
        hi = _coerce_scalar(value[1], col_type)
        return (lo, hi)
    if operator == "is_null":
        return _coerce_scalar(value, "bool") if value is not None else True
    if operator in ("len_eq", "len_gt", "len_gte", "len_lt", "len_lte"):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return _coerce_scalar(value, col_type)


# ---------------------------------------------------------------------------
# Operator → Q
# ---------------------------------------------------------------------------

def _build_q(orm_path: str, operator: str, value: Any, col_type: str) -> Optional[Q]:
    """Build a single Q node for a single filter row."""
    if value is None and operator not in ("is_null", "is_empty"):
        return None

    if operator == "eq":
        return Q(**{orm_path: value})
    if operator == "neq":
        return ~Q(**{orm_path: value})
    if operator == "gt":
        return Q(**{f"{orm_path}__gt": value})
    if operator == "gte":
        return Q(**{f"{orm_path}__gte": value})
    if operator == "lt":
        return Q(**{f"{orm_path}__lt": value})
    if operator == "lte":
        return Q(**{f"{orm_path}__lte": value})
    if operator == "contains":
        return Q(**{f"{orm_path}__contains": value})
    if operator == "icontains":
        return Q(**{f"{orm_path}__icontains": value})
    if operator == "startswith":
        return Q(**{f"{orm_path}__startswith": value})
    if operator == "istartswith":
        return Q(**{f"{orm_path}__istartswith": value})
    if operator == "in":
        if not value:
            # empty `in` should match nothing — use impossible Q
            return Q(pk__in=[])
        return Q(**{f"{orm_path}__in": value})
    if operator == "between":
        if not value or value[0] is None or value[1] is None:
            return None
        lo, hi = value
        return Q(**{f"{orm_path}__gte": lo}) & Q(**{f"{orm_path}__lte": hi})
    if operator == "is_null":
        return Q(**{f"{orm_path}__isnull": bool(value)})
    # Array-specific operators (Postgres ArrayField)
    if operator == "overlap":
        if not value:
            return None
        return Q(**{f"{orm_path}__overlap": value})
    if operator == "len_eq":
        return Q(**{f"{orm_path}__len": value})
    if operator == "len_gt":
        return Q(**{f"{orm_path}__len__gt": value})
    if operator == "len_gte":
        return Q(**{f"{orm_path}__len__gte": value})
    if operator == "len_lt":
        return Q(**{f"{orm_path}__len__lt": value})
    if operator == "len_lte":
        return Q(**{f"{orm_path}__len__lte": value})
    if operator == "is_empty":
        return Q(**{f"{orm_path}__len": 0})

    return None


# ---------------------------------------------------------------------------
# Recursive compiler
# ---------------------------------------------------------------------------

def _compile_node(node: Dict[str, Any], columns: Dict[str, Dict[str, Any]],
                  warnings: List[str]) -> Q:
    """Recursively compile one filter node (group or leaf) to a Q object."""
    if not isinstance(node, dict):
        return Q()

    # Group node: has "filters" list + "operator" ("and"/"or")
    if "filters" in node:
        join = str(node.get("operator", "and")).lower()
        child_qs: List[Q] = []
        for child in node.get("filters") or []:
            if not isinstance(child, dict):
                continue
            if child.get("disabled"):
                continue
            q = _compile_node(child, columns, warnings)
            if q and q.children:
                child_qs.append(q)
        if not child_qs:
            return Q()
        combined = child_qs[0]
        for q in child_qs[1:]:
            combined = (combined | q) if join == "or" else (combined & q)
        return combined

    # Leaf node
    column_id = node.get("column_id") or node.get("columnId")
    operator = node.get("operator")
    if not column_id or not operator:
        return Q()

    spec = columns.get(column_id)
    if not spec:
        warnings.append(f"unknown column: {column_id}")
        return Q()

    if operator not in spec.get("operators", ()):
        warnings.append(f"operator {operator!r} not allowed on column {column_id!r}")
        return Q()

    coerced = _coerce_value(node.get("value"), spec.get("type", "string"), operator)
    q = _build_q(spec["orm_path"], operator, coerced, spec.get("type", "string"))
    if q is None:
        warnings.append(f"could not coerce value for {column_id}/{operator}")
        return Q()
    return q


def compile_stack(stack: Optional[Dict[str, Any]], kind: str) -> Q:
    """Compile a filter stack into a Q. Returns empty Q() on invalid input."""
    if not stack:
        return Q()
    columns = get_columns(kind)
    if not columns:
        return Q()
    warnings: List[str] = []
    return _compile_node(stack, columns, warnings)


def compile_stack_report(stack: Optional[Dict[str, Any]], kind: str) -> Tuple[Q, List[str]]:
    """Same as compile_stack but also returns any warnings emitted."""
    if not stack:
        return Q(), []
    columns = get_columns(kind)
    if not columns:
        return Q(), [f"unknown kind: {kind}"]
    warnings: List[str] = []
    q = _compile_node(stack, columns, warnings)
    return q, warnings


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def apply_stack(queryset, stack: Optional[Dict[str, Any]], kind: str):
    """Apply a filter stack to a queryset and return the filtered queryset."""
    q, _ = compile_stack_report(stack, kind)
    if not q.children:
        return queryset
    return queryset.filter(q).distinct()


def resolve_ids(queryset, stack: Optional[Dict[str, Any]], kind: str,
                max_count: Optional[int] = None) -> List[int]:
    """Resolve a stack against a queryset into a flat list of primary keys.

    If `max_count` is set and the stack would exceed it, a ValueError is raised —
    callers should guard against runaway queries.
    """
    qs = apply_stack(queryset, stack, kind).values_list("id", flat=True)
    if max_count is not None:
        ids = list(qs[: max_count + 1])
        if len(ids) > max_count:
            raise ValueError(f"filter resolved to more than {max_count} ids")
        return ids
    return list(qs)


def merge_ids(explicit_ids: Optional[List[int]],
              filter_ids: Optional[List[int]],
              mode: str = "append") -> List[int]:
    """Merge explicit IDs from the request with IDs resolved from a filter stack.

    Modes:
      * append      — union of both (default)
      * replace     — use filter_ids if present, else explicit_ids
      * intersect   — intersection (for narrowing a large filter set
                      to a user's explicit selection)
    """
    explicit_ids = list(explicit_ids or [])
    filter_ids = list(filter_ids or [])

    if not explicit_ids and not filter_ids:
        return []

    if mode == "replace":
        return filter_ids if filter_ids else explicit_ids
    if mode == "intersect":
        if not explicit_ids:
            return filter_ids
        if not filter_ids:
            return explicit_ids
        s = set(explicit_ids)
        return [i for i in filter_ids if i in s]
    # default: append / union, preserve order
    seen = set()
    out: List[int] = []
    for i in list(explicit_ids) + list(filter_ids):
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
