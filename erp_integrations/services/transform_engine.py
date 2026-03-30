"""
Pure transform engine for ERP API responses.

- Record extraction: locate the records array in JSON
- Config validation: ensure transform_config is well-formed
- Phase 2: explode, derived dates (spec'd but not implemented yet)
"""

from typing import Any, Dict, List, Optional, Tuple

DEFAULT_TRANSFORM_CONFIG = {
    "records": {
        "path": None,
        "fallbackPaths": [],
        "autoDiscover": True,
        "rootAsOneRow": False,
    },
    "explode": {
        "enabled": False,
        "rules": [],
        "maxRowsPerItem": 500,
    },
    "derivedDates": {
        "rules": [],
        "inputDateFormat": "dd/MM/yyyy",
        "inputTimeFormat": "HH:mm:ss",
    },
}


class RecordExtractionError(Exception):
    """Raised when no record array can be found in the response."""

    pass


def deep_merge(default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge override into default. Arrays are replaced, not merged."""
    result = dict(default)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def get_by_dot_path(obj: Any, path: str) -> Any:
    """
    Traverse nested JSON by dot-path. Supports numeric indexes for arrays.
    E.g. get_by_dot_path(data, "a.b.0.c") -> data["a"]["b"][0]["c"]
    """
    if not path:
        return obj
    parts = path.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        try:
            idx = int(part)
            if isinstance(current, list):
                current = current[idx] if 0 <= idx < len(current) else None
            else:
                return None
        except ValueError:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
    return current


VALID_ON_DUPLICATE = frozenset({"update", "flag", "add"})


def extract_external_id(
    record: Dict[str, Any],
    unique_id_config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Build a string id from an API item using ERPAPIDefinition.unique_id_config.
    Reuses get_by_dot_path for each path segment.
    """
    if not unique_id_config or not isinstance(unique_id_config, dict):
        return None
    mode = unique_id_config.get("mode")
    if mode == "single_path":
        path = unique_id_config.get("path")
        if not path or not isinstance(path, str):
            return None
        val = get_by_dot_path(record, path.strip())
        if val is None:
            return None
        return str(val).strip() or None
    if mode == "composite":
        paths = unique_id_config.get("paths") or []
        if not isinstance(paths, list):
            return None
        sep = unique_id_config.get("separator")
        if sep is None:
            sep = "|"
        if not isinstance(sep, str):
            sep = "|"
        parts: List[str] = []
        for p in paths:
            if not p or not isinstance(p, str):
                continue
            val = get_by_dot_path(record, p.strip())
            parts.append(str(val) if val is not None else "")
        if not parts:
            return None
        out = sep.join(parts).strip()
        return out or None
    return None


def validate_unique_id_config(config: Any) -> List[Dict[str, str]]:
    """
    Validate unique_id_config on ERPAPIDefinition.
    Returns list of {"field": str, "message": str} for each error.
    """
    errors: List[Dict[str, str]] = []

    if config is None:
        return errors
    if not isinstance(config, dict):
        errors.append({"field": "unique_id_config", "message": "Config must be a JSON object or null."})
        return errors

    mode = config.get("mode")
    if mode not in ("single_path", "composite"):
        errors.append(
            {
                "field": "mode",
                "message": "mode must be 'single_path' or 'composite'.",
            }
        )
        return errors

    on_dup = config.get("on_duplicate", "update")
    if on_dup not in VALID_ON_DUPLICATE:
        errors.append(
            {
                "field": "on_duplicate",
                "message": f"on_duplicate must be one of: {', '.join(sorted(VALID_ON_DUPLICATE))}.",
            }
        )

    if mode == "single_path":
        path = config.get("path")
        if not path or not isinstance(path, str) or not str(path).strip():
            errors.append({"field": "path", "message": "path is required and must be a non-empty string for single_path."})
    else:
        paths = config.get("paths")
        if paths is None or not isinstance(paths, list):
            errors.append({"field": "paths", "message": "paths must be a non-empty array for composite."})
        elif not paths:
            errors.append({"field": "paths", "message": "paths must contain at least one path string for composite."})
        else:
            for i, p in enumerate(paths):
                if not p or not isinstance(p, str) or not str(p).strip():
                    errors.append(
                        {"field": f"paths[{i}]", "message": "Each path must be a non-empty string."},
                    )

    sep = config.get("separator")
    if sep is not None and not isinstance(sep, str):
        errors.append({"field": "separator", "message": "separator must be a string if set."})

    return errors


def _is_record_array(val: Any) -> bool:
    """Return True if val is a non-empty list of dicts."""
    if not isinstance(val, list):
        return False
    if not val:
        return False
    return all(isinstance(x, dict) for x in val)


def _auto_discover_array(data: Dict[str, Any]) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Find the first top-level key whose value is a list of dicts.
    Returns (key_name, items) or None.
    """
    if not isinstance(data, dict):
        return None
    for k, v in data.items():
        if _is_record_array(v):
            return (k, v)
    return None


def pick_items_array(
    data: Any,
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract the records array from API response using transform config.

    Uses config["records"]:
    - path: primary path to the array (e.g. "produto_servico_cadastro")
    - fallbackPaths: try these if path fails
    - autoDiscover: if True, scan top-level keys for first list-of-dicts
    - rootAsOneRow: if True and no array found, return [data]

    Raises RecordExtractionError if no array found and rootAsOneRow is False.
    """
    merged = deep_merge(DEFAULT_TRANSFORM_CONFIG, config or {})
    rec = merged.get("records", {}) or {}
    path = rec.get("path")
    fallback_paths = rec.get("fallbackPaths") or []
    auto_discover = rec.get("autoDiscover", True)
    root_as_one_row = rec.get("rootAsOneRow", False)

    candidates: List[str] = []
    if path:
        candidates.append(path)
    candidates.extend(fallback_paths)

    for p in candidates:
        items = get_by_dot_path(data, p)
        if _is_record_array(items):
            return items

    if auto_discover:
        found = _auto_discover_array(data)
        if found:
            return found[1]

    if root_as_one_row:
        if isinstance(data, dict):
            return [data]
        return [{"_root": data}]

    raise RecordExtractionError(
        f"No record array found. Tried paths: {candidates!r}, autoDiscover={auto_discover}, rootAsOneRow={root_as_one_row}"
    )


def validate_transform_config(config: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Validate transform_config structure.
    Returns list of {"field": str, "message": str} for each error.
    """
    errors: List[Dict[str, str]] = []

    if not isinstance(config, dict):
        errors.append({"field": "transform_config", "message": "Config must be a JSON object."})
        return errors

    rec = config.get("records")
    if rec is not None:
        if not isinstance(rec, dict):
            errors.append({"field": "records", "message": "records must be an object."})
        elif rec.get("path") is not None:
            p = rec.get("path")
            if not isinstance(p, str) or not p.strip():
                errors.append({"field": "records.path", "message": "records.path must be a non-empty string."})

    explode = config.get("explode")
    if explode is not None:
        if not isinstance(explode, dict):
            errors.append({"field": "explode", "message": "explode must be an object."})
        else:
            rules = explode.get("rules", [])
            if not isinstance(rules, list):
                errors.append({"field": "explode.rules", "message": "explode.rules must be an array."})
            else:
                for i, r in enumerate(rules):
                    if not isinstance(r, dict):
                        errors.append({"field": f"explode.rules[{i}]", "message": "Each rule must be an object."})
                        continue
                    path = r.get("path")
                    if not path or not str(path).strip():
                        errors.append({"field": f"explode.rules[{i}].path", "message": "path is required and must be non-empty."})
                    max_len = r.get("maxLen")
                    if max_len is not None:
                        try:
                            v = int(max_len)
                            if v < 1 or v > 10000:
                                errors.append({"field": f"explode.rules[{i}].maxLen", "message": "maxLen must be between 1 and 10000."})
                        except (TypeError, ValueError):
                            errors.append({"field": f"explode.rules[{i}].maxLen", "message": "maxLen must be an integer."})
                    prefix = r.get("prefix")
                    if prefix is not None and len(str(prefix)) > 20:
                        errors.append({"field": f"explode.rules[{i}].prefix", "message": "prefix must be at most 20 characters."})
            mri = explode.get("maxRowsPerItem")
            if mri is not None:
                try:
                    v = int(mri)
                    if v < 1 or v > 50000:
                        errors.append({"field": "explode.maxRowsPerItem", "message": "maxRowsPerItem must be between 1 and 50000."})
                except (TypeError, ValueError):
                    errors.append({"field": "explode.maxRowsPerItem", "message": "maxRowsPerItem must be an integer."})

    dd = config.get("derivedDates")
    if dd is not None:
        if not isinstance(dd, dict):
            errors.append({"field": "derivedDates", "message": "derivedDates must be an object."})
        else:
            rules = dd.get("rules", [])
            if not isinstance(rules, list):
                errors.append({"field": "derivedDates.rules", "message": "derivedDates.rules must be an array."})
            else:
                for i, r in enumerate(rules):
                    if not isinstance(r, dict):
                        errors.append({"field": f"derivedDates.rules[{i}]", "message": "Each rule must be an object."})
                        continue
                    mode = r.get("mode")
                    if mode not in ("date_only", "date_time"):
                        errors.append({"field": f"derivedDates.rules[{i}].mode", "message": "mode must be 'date_only' or 'date_time'."})
                    elif mode == "date_time" and not r.get("sourceTime"):
                        errors.append({"field": f"derivedDates.rules[{i}].sourceTime", "message": "sourceTime is required when mode is 'date_time'."})

    return errors
