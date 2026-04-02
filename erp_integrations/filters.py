"""
Filters for ERP integrations API (django-filter + dynamic JSONField path filters).
"""

from __future__ import annotations

import json
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import QueryDict
from django_filters import rest_framework as filters

from .models import ERPRawRecord

SEGMENT_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Last segment can be a JSON lookup; must match Django JSONField / ORM suffixes we allow.
JSON_LOOKUP_SUFFIXES = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "startswith",
        "endswith",
        "gte",
        "lte",
        "gt",
        "lt",
        "in",
        "isnull",
    }
)

# Query params reserved for pagination / DRF / this API (not JSON path filters).
RESERVED_QUERY_KEYS = frozenset(
    {
        "paginated",
        "page",
        "page_size",
        "limit",
        "ordering",
        "search",
        "format",
    }
)

JSON_FIELD_PREFIXES = ("data__", "page_response_header__")


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    pass


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    pass


def _valid_segment(seg: str) -> bool:
    return bool(seg and SEGMENT_RE.match(seg))


def _parse_json_param_key(key: str, root: str) -> tuple[str, str]:
    """
    Parse a query key like data__a__b__icontains into (orm_lookup, last_lookup_name).

    root is 'data' or 'page_response_header'.
    """
    prefix = f"{root}__"
    if not key.startswith(prefix):
        raise ValidationError(f"Invalid key prefix: {key!r}")
    rest = key[len(prefix) :]
    if not rest:
        raise ValidationError(f"Empty path after {root!r}")

    parts = rest.split("__")
    if not all(_valid_segment(p) for p in parts):
        raise ValidationError(f"Invalid path segment in {key!r}")

    if len(parts) >= 2 and parts[-1] in JSON_LOOKUP_SUFFIXES:
        lookup = parts[-1]
        path_parts = parts[:-1]
        if not path_parts:
            raise ValidationError(f"Missing JSON path in {key!r}")
    else:
        lookup = "exact"
        path_parts = parts

    orm_path = "__".join([root, *path_parts])
    if lookup != "exact":
        orm_lookup = f"{orm_path}__{lookup}"
    else:
        orm_lookup = orm_path
    return orm_lookup, lookup


def _coerce_value(raw: str, lookup: str) -> Any:
    s = raw.strip()
    if lookup == "isnull":
        low = s.lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
        raise ValidationError("isnull expects true or false")

    if lookup == "in":
        parts = [p.strip() for p in s.split(",") if p.strip() != ""]
        return [_coerce_scalar(p) for p in parts]

    if lookup == "contains":
        # JSON subset / array containment: try JSON first
        s_stripped = s.strip()
        if s_stripped.startswith(("{", "[")):
            try:
                return json.loads(s_stripped)
            except json.JSONDecodeError as e:
                raise ValidationError(f"Invalid JSON for contains: {e}") from e
        return _coerce_scalar(s)

    return _coerce_scalar(s)


def _coerce_scalar(s: str) -> Any:
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null" or low == "none":
        return None
    try:
        if s.startswith("-") and s[1:].isdigit():
            return int(s)
        if s.isdigit():
            return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def apply_json_field_filters(queryset: QuerySet, query_params: QueryDict) -> QuerySet:
    """
    Apply AND filters for keys starting with data__ or page_response_header__.
    Path segments must be [A-Za-z0-9_]+. Optional trailing lookup suffix from JSON_LOOKUP_SUFFIXES.

    Raises ValidationError if a JSON filter key is malformed or values cannot be coerced.
    """
    if not query_params:
        return queryset

    from django.db.models import Q

    qs = queryset
    for key in query_params:
        if key in RESERVED_QUERY_KEYS:
            continue
        if not key.startswith(JSON_FIELD_PREFIXES):
            continue

        root = "data" if key.startswith("data__") else "page_response_header"
        orm_lookup, lookup = _parse_json_param_key(key, root)

        raw_values = query_params.getlist(key)
        if not raw_values:
            continue

        q_combo = Q()
        for raw in raw_values:
            val = _coerce_value(raw, lookup)
            q_combo |= Q(**{orm_lookup: val})
        qs = qs.filter(q_combo)
    return qs


class ERPRawRecordFilter(filters.FilterSet):
    """Filters on ERPRawRecord scalar / FK fields (not dynamic JSON paths)."""

    id = filters.NumberFilter()
    id__in = NumberInFilter(field_name="id", lookup_expr="in")

    sync_run = filters.NumberFilter(field_name="sync_run_id")
    company = filters.NumberFilter(field_name="company_id")

    api_call = filters.CharFilter(lookup_expr="exact")
    api_call__in = CharInFilter(field_name="api_call", lookup_expr="in")
    api_call__icontains = filters.CharFilter(field_name="api_call", lookup_expr="icontains")

    external_id = filters.CharFilter(lookup_expr="exact")
    external_id__isnull = filters.BooleanFilter(field_name="external_id", lookup_expr="isnull")

    record_hash = filters.CharFilter(lookup_expr="exact")
    page_number = filters.NumberFilter()
    record_index = filters.NumberFilter()
    global_index = filters.NumberFilter()
    page_records_count = filters.NumberFilter()
    total_pages = filters.NumberFilter()
    total_records = filters.NumberFilter()

    is_duplicate = filters.BooleanFilter()

    fetched_at__gte = filters.IsoDateTimeFilter(field_name="fetched_at", lookup_expr="gte")
    fetched_at__lte = filters.IsoDateTimeFilter(field_name="fetched_at", lookup_expr="lte")

    ordering = filters.OrderingFilter(
        fields=(
            ("id", "id"),
            ("fetched_at", "fetched_at"),
            ("global_index", "global_index"),
            ("api_call", "api_call"),
            ("page_number", "page_number"),
        )
    )

    class Meta:
        model = ERPRawRecord
        fields = []
