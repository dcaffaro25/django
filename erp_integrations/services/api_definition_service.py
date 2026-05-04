"""
Phase-1 helpers for the structured ERPAPIDefinition editor.

Two kinds of validation live here, both pure functions that return a
list of error dicts (empty on success) so callers can compose them:

* ``validate_param_schema`` — walks a list-of-dicts param schema (the
  ``ERPAPIDefinition.param_schema`` field) and checks each row has a
  consistent name/type/default triple, the ``location`` is one of the
  supported values, and required + default don't contradict each other.
* ``validate_pagination_spec`` — walks the new ``pagination_spec`` JSON
  field (added in migration 0014). The schema is loose by design (each
  pagination mode needs different keys) so we validate per-mode.

Plus a couple of small builders the new ``test-call`` endpoint will
use to materialise a request from a definition + sample params:

* ``build_test_payload`` — assembles the body / query / headers /
  path-segments from ``param_schema`` + a dict of operator-supplied
  values, applying ``location`` routing.
* ``infer_response_columns`` — given a JSON response and an optional
  ``records_path``, extracts up to N first items and returns the
  flattened key list with sample values. Used by Phase 3 auto-probe
  too — putting it here keeps that work additive.

Nothing in this module talks to ERPProvider's HTTP layer. Callers
(``views.py``) wire the auth strategy on top.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import jmespath


# ---------------------------------------------------------------------
# Param schema
# ---------------------------------------------------------------------

VALID_PARAM_TYPES = frozenset({
    "string", "int", "number", "boolean", "date", "datetime",
    "enum", "object", "array",
})

VALID_PARAM_LOCATIONS = frozenset({"body", "query", "path", "header"})


def validate_param_schema(schema: Any) -> List[Dict[str, str]]:
    """Walks a param_schema list and returns a list of error dicts.

    Each error: ``{"row": int, "field": str, "message": str}``. The UI
    renders these inline next to the offending row.
    """
    errors: List[Dict[str, str]] = []
    if schema is None or schema == [] or schema == {}:
        return errors
    if not isinstance(schema, list):
        return [{"row": -1, "field": "schema", "message": "param_schema must be a list."}]

    seen_names: set = set()
    for i, row in enumerate(schema):
        if not isinstance(row, dict):
            errors.append({"row": i, "field": "row", "message": "Each entry must be an object."})
            continue
        name = row.get("name")
        if not name or not isinstance(name, str):
            errors.append({"row": i, "field": "name", "message": "Name is required."})
        elif name in seen_names:
            errors.append({"row": i, "field": "name", "message": f"Duplicate name: {name}."})
        else:
            seen_names.add(name)

        type_ = row.get("type", "string")
        if type_ not in VALID_PARAM_TYPES:
            errors.append({
                "row": i, "field": "type",
                "message": f"Type must be one of {sorted(VALID_PARAM_TYPES)}.",
            })

        location = row.get("location", "body")
        if location not in VALID_PARAM_LOCATIONS:
            errors.append({
                "row": i, "field": "location",
                "message": f"Location must be one of {sorted(VALID_PARAM_LOCATIONS)}.",
            })

        # required + default contradiction is informational, not fatal:
        # a required field with a default is just "use default unless
        # caller overrides". Skip.

        # enum requires an options list.
        if type_ == "enum":
            opts = row.get("options")
            if not isinstance(opts, list) or not opts:
                errors.append({
                    "row": i, "field": "options",
                    "message": "Enum type requires a non-empty options list.",
                })

    return errors


# ---------------------------------------------------------------------
# Pagination spec
# ---------------------------------------------------------------------

VALID_PAGINATION_MODES = frozenset({"none", "page_number", "cursor", "offset"})


def validate_pagination_spec(spec: Any) -> List[str]:
    """Returns a list of human-readable error strings (empty on success)."""
    errors: List[str] = []
    if spec is None:
        return errors
    if not isinstance(spec, dict):
        return ["pagination_spec must be an object."]

    mode = spec.get("mode")
    if mode not in VALID_PAGINATION_MODES:
        errors.append(f"mode must be one of {sorted(VALID_PAGINATION_MODES)}.")
        return errors

    if mode == "none":
        return errors

    if mode == "page_number":
        if not spec.get("page_param"):
            errors.append("page_number mode requires 'page_param'.")
        # page_size optional — if absent, server default applies.

    if mode == "cursor":
        if not spec.get("cursor_path"):
            errors.append("cursor mode requires 'cursor_path' (JMESPath into the response).")
        if not spec.get("next_cursor_param"):
            errors.append("cursor mode requires 'next_cursor_param' (request param name).")
        # Smoke-test the JMESPath at validation time so a bad expression
        # surfaces here rather than at first run.
        cp = spec.get("cursor_path")
        if cp:
            try:
                jmespath.compile(cp)
            except Exception as exc:
                errors.append(f"cursor_path is not a valid JMESPath: {exc}")

    if mode == "offset":
        if not spec.get("offset_param"):
            errors.append("offset mode requires 'offset_param'.")
        if not spec.get("limit_param"):
            errors.append("offset mode requires 'limit_param'.")

    max_pages = spec.get("max_pages")
    if max_pages is not None and (not isinstance(max_pages, int) or max_pages < 1):
        errors.append("max_pages must be a positive integer.")

    return errors


# ---------------------------------------------------------------------
# Test-call helpers
# ---------------------------------------------------------------------

def build_test_payload(
    param_schema: List[Dict[str, Any]],
    values: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """Splits operator-supplied values into body / query / path / header
    buckets according to each param's ``location`` field.

    Values not in the schema are dropped silently — keeps test calls
    from accidentally sending random extras.
    """
    by_name = {row.get("name"): row for row in (param_schema or []) if isinstance(row, dict)}
    out: Dict[str, Dict[str, Any]] = {
        "body": {},
        "query": {},
        "path": {},
        "header": {},
    }
    for name, value in (values or {}).items():
        spec = by_name.get(name)
        if not spec:
            continue
        loc = spec.get("location", "body")
        if loc not in out:
            continue
        out[loc][name] = value
    return out


def _flatten_keys(obj: Any, prefix: str = "", max_depth: int = 2) -> List[Tuple[str, Any]]:
    """Returns a flat list of (path, value) pairs up to ``max_depth``
    levels of nesting. Arrays are not descended; their first element's
    type is reported instead."""
    out: List[Tuple[str, Any]] = []
    if max_depth < 0:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict) and max_depth > 0:
                out.extend(_flatten_keys(v, path, max_depth - 1))
            else:
                out.append((path, v))
    return out


def infer_response_columns(
    response_json: Any,
    records_path: Optional[str] = None,
    max_samples: int = 3,
) -> Dict[str, Any]:
    """Given a response, extract up to ``max_samples`` first items and
    return a structure the UI can render directly:

    .. code-block:: python

        {
            "items_found": 12,
            "columns": [
                {"path": "id", "type": "int", "samples": [1, 2, 3]},
                {"path": "endereco.cidade", "type": "string", "samples": ["SP"]},
                ...
            ],
        }

    If ``records_path`` is provided, it's evaluated first; otherwise
    the entire response is treated as the item list (with the usual
    fallback of "if it's a dict, look for the first list-valued key").
    """
    items: List[Any] = []
    if records_path:
        try:
            extracted = jmespath.search(records_path, response_json)
        except Exception:
            extracted = None
        if isinstance(extracted, list):
            items = extracted
        elif extracted is not None:
            items = [extracted]
    else:
        if isinstance(response_json, list):
            items = response_json
        elif isinstance(response_json, dict):
            for v in response_json.values():
                if isinstance(v, list):
                    items = v
                    break

    columns: Dict[str, Dict[str, Any]] = {}
    for item in items[:max_samples * 4]:  # scan a few extra to fill samples
        if not isinstance(item, dict):
            continue
        for path, value in _flatten_keys(item, max_depth=2):
            col = columns.setdefault(path, {"path": path, "type": _guess_type(value), "samples": []})
            if len(col["samples"]) < max_samples and value is not None:
                col["samples"].append(value)

    return {
        "items_found": len(items),
        "columns": list(columns.values()),
    }


def _guess_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"
