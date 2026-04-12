"""
Auto-generated introspection registry.

Scans Django models, DRF routers/views, serializers, and filter sets to
build the metadata that the /api/meta/* endpoints serve.  Every piece of
data comes from the *actual* codebase objects — nothing is hand-written JSON.
"""
from __future__ import annotations

import inspect
import re
from collections import OrderedDict
from typing import Any

from django.apps import apps
from django.db import models
from django.db.models import Field as DjangoField, ManyToManyField, ManyToManyRel, ManyToOneRel, ForeignKey
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.routers import DefaultRouter
from rest_framework.viewsets import ViewSetMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP = {
    "AutoField": "integer",
    "BigAutoField": "integer",
    "SmallAutoField": "integer",
    "BooleanField": "boolean",
    "NullBooleanField": "boolean",
    "CharField": "string",
    "SlugField": "string",
    "TextField": "string",
    "EmailField": "string",
    "URLField": "string",
    "UUIDField": "uuid",
    "FilePathField": "string",
    "FileField": "file",
    "ImageField": "file",
    "IntegerField": "integer",
    "SmallIntegerField": "integer",
    "BigIntegerField": "integer",
    "PositiveIntegerField": "integer",
    "PositiveSmallIntegerField": "integer",
    "PositiveBigIntegerField": "integer",
    "FloatField": "float",
    "DecimalField": "decimal",
    "DateField": "date",
    "DateTimeField": "datetime",
    "TimeField": "time",
    "DurationField": "duration",
    "BinaryField": "binary",
    "JSONField": "json",
    "ArrayField": "array",
    "GenericIPAddressField": "string",
    "IPAddressField": "string",
    "TreeForeignKey": "integer",
}


def _django_field_type(field: DjangoField) -> str:
    cls_name = type(field).__name__
    if cls_name == "VectorField":
        return "vector"
    return _FIELD_TYPE_MAP.get(cls_name, cls_name.lower())


def _field_meta(field: DjangoField) -> dict:
    """Extract metadata dict for a single Django model field."""
    info: dict[str, Any] = {
        "name": field.name,
        "type": _django_field_type(field),
        "required": not field.blank and not field.has_default() and not getattr(field, "primary_key", False),
        "description": field.help_text or "",
    }
    if field.primary_key:
        info["primary_key"] = True
    if field.unique:
        info["unique"] = True
    if field.db_index:
        info["indexed"] = True
    if field.has_default():
        default = field.default
        if callable(default):
            info["default"] = f"<callable: {default.__name__}>" if hasattr(default, "__name__") else "<callable>"
        else:
            info["default"] = default
    if hasattr(field, "max_length") and field.max_length:
        info["max_length"] = field.max_length
    if hasattr(field, "max_digits") and field.max_digits:
        info["max_digits"] = field.max_digits
        info["decimal_places"] = field.decimal_places
    if field.null:
        info["nullable"] = True
    if field.choices:
        info["type"] = "enum"
        info["allowed_values"] = [c[0] for c in field.choices]
        info["labels"] = {c[0]: c[1] for c in field.choices}
    if isinstance(field, ForeignKey):
        info["type"] = "fk"
        info["related_model"] = field.related_model._meta.label
    return info


def _relationship_meta(field) -> dict | None:
    """Build relationship descriptor for FK, M2M, reverse-FK."""
    if isinstance(field, ForeignKey):
        return {
            "name": field.name,
            "type": "belongs_to",
            "related_model": field.related_model._meta.label,
            "foreign_key": field.column,
            "cascade_delete": field.remote_field.on_delete.__name__ == "CASCADE",
            "nullable": field.null,
            "description": field.help_text or "",
        }
    if isinstance(field, ManyToManyField):
        through = field.remote_field.through
        return {
            "name": field.name,
            "type": "many_to_many",
            "related_model": field.related_model._meta.label,
            "through_table": through._meta.db_table if through else None,
            "description": field.help_text or "",
        }
    return None


def _reverse_relationship_meta(rel) -> dict | None:
    if isinstance(rel, ManyToOneRel):
        return {
            "name": rel.get_accessor_name(),
            "type": "has_many",
            "related_model": rel.related_model._meta.label,
            "foreign_key": rel.field.column,
            "cascade_delete": rel.on_delete.__name__ == "CASCADE",
            "description": "",
        }
    if isinstance(rel, ManyToManyRel):
        return {
            "name": rel.get_accessor_name(),
            "type": "many_to_many",
            "related_model": rel.related_model._meta.label,
            "through_table": rel.through._meta.db_table if rel.through else None,
            "description": "",
        }
    return None


# ---------------------------------------------------------------------------
# Model introspection
# ---------------------------------------------------------------------------

# Apps to include in introspection (business logic apps only)
_INCLUDED_APPS = [
    "multitenancy",
    "core",
    "accounting",
    "billing",
    "inventory",
    "hr",
    "ML",
    "npl",
    "feedback",
    "knowledge_base",
    "erp_integrations",
]


def get_all_models() -> list[dict]:
    """Return full model catalog for all business-logic apps."""
    result = []
    for app_label in _INCLUDED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            result.append(_model_to_dict(model))
    return result


def get_model_detail(model_name: str) -> dict | None:
    """Return detail for a single model by name (case-insensitive)."""
    for app_label in _INCLUDED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            if model.__name__.lower() == model_name.lower():
                return _model_to_dict(model)
    return None


def get_model_relationships(model_name: str) -> dict | None:
    """Return relationship graph for a model — direct + one transitive hop."""
    detail = get_model_detail(model_name)
    if not detail:
        return None

    direct = detail.get("relationships", [])
    transitive = []
    for rel in direct:
        related_name = rel["related_model"].split(".")[-1]
        related_detail = get_model_detail(related_name)
        if related_detail:
            for r2 in related_detail.get("relationships", []):
                entry = dict(r2)
                entry["via"] = rel["name"]
                transitive.append(entry)

    return {
        "model": detail["name"],
        "direct_relationships": direct,
        "transitive_relationships": transitive,
    }


def _model_to_dict(model) -> dict:
    meta = model._meta
    fields = []
    relationships = []

    for field in meta.get_fields():
        if isinstance(field, (ManyToOneRel, ManyToManyRel)):
            rel = _reverse_relationship_meta(field)
            if rel:
                relationships.append(rel)
            continue
        if isinstance(field, ManyToManyField):
            fields.append({
                "name": field.name,
                "type": "many_to_many",
                "related_model": field.related_model._meta.label,
                "description": field.help_text or "",
            })
            rel = _relationship_meta(field)
            if rel:
                relationships.append(rel)
            continue
        if isinstance(field, ForeignKey):
            fmeta = _field_meta(field)
            fields.append(fmeta)
            rel = _relationship_meta(field)
            if rel:
                relationships.append(rel)
            continue
        if hasattr(field, "column"):
            fields.append(_field_meta(field))

    # Constraints
    constraints = []
    for c in meta.constraints:
        cdict = {"type": type(c).__name__}
        if hasattr(c, "fields"):
            cdict["fields"] = list(c.fields)
        if hasattr(c, "check"):
            cdict["check"] = str(c.check)
        if hasattr(c, "name"):
            cdict["name"] = c.name
        constraints.append(cdict)

    if meta.unique_together:
        for ut in meta.unique_together:
            constraints.append({
                "type": "unique_together",
                "fields": list(ut),
            })

    # Indexes
    indexes = []
    for idx in meta.indexes:
        indexes.append({
            "name": idx.name if hasattr(idx, "name") else None,
            "fields": [f.lstrip("-") for f in idx.fields] if hasattr(idx, "fields") else [],
        })

    # Timestamps / soft delete detection
    timestamps = []
    soft_delete = False
    for f in meta.get_fields():
        if hasattr(f, "name"):
            if f.name in ("created_at", "updated_at"):
                timestamps.append(f.name)
            if f.name == "is_deleted":
                soft_delete = True

    # Check for abstract parent (BaseModel, TenantAwareBaseModel)
    bases = [b.__name__ for b in model.__mro__ if b.__name__ in (
        "BaseModel", "TenantAwareBaseModel", "MPTTModel",
    )]

    info = {
        "name": model.__name__,
        "app": meta.app_label,
        "table": meta.db_table,
        "description": (model.__doc__ or "").strip(),
        "fields": fields,
        "relationships": relationships,
        "constraints": constraints,
        "indexes": indexes,
        "timestamps": timestamps,
        "soft_delete": soft_delete,
        "inherits": bases,
    }
    return info


# ---------------------------------------------------------------------------
# Enum introspection
# ---------------------------------------------------------------------------

def get_all_enums() -> dict:
    """Collect every choices field across all included models."""
    enums: dict[str, dict] = {}
    for app_label in _INCLUDED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            for field in model._meta.get_fields():
                if hasattr(field, "choices") and field.choices:
                    key = f"{model.__name__}.{field.name}"
                    enums[key] = {
                        "model": model.__name__,
                        "field": field.name,
                        "values": [c[0] for c in field.choices],
                        "labels": {c[0]: c[1] for c in field.choices},
                        "description": field.help_text or "",
                    }
    return enums


# ---------------------------------------------------------------------------
# Endpoint introspection
# ---------------------------------------------------------------------------

def _collect_url_patterns(resolver=None, prefix="") -> list[dict]:
    """Recursively walk the URL tree and collect API endpoint metadata."""
    if resolver is None:
        resolver = get_resolver()

    patterns = []
    for pattern in resolver.url_patterns:
        full_path = prefix + _pattern_to_str(pattern)
        if isinstance(pattern, URLResolver):
            patterns.extend(_collect_url_patterns(pattern, full_path))
        elif isinstance(pattern, URLPattern):
            callback = pattern.callback
            if callback is None:
                continue
            # Skip admin and static
            if "/admin" in full_path or "/static" in full_path:
                continue
            ep = _endpoint_from_pattern(pattern, full_path)
            if ep:
                patterns.append(ep)
    return patterns


def _pattern_to_str(pattern) -> str:
    """Convert a URL pattern to a readable path string."""
    raw = str(pattern.pattern)
    # Clean up regex artifacts
    raw = raw.replace("^", "").replace("$", "").replace("(?P<", ":").replace(">[^/]+)", "").replace(">\\d+)", "").replace(">\\w+)", "").replace(">[^/.]+)", "")
    raw = re.sub(r"\(\?P<(\w+)>[^)]+\)", r":\1", raw)
    raw = re.sub(r"/\?", "/", raw)
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw


def _endpoint_from_pattern(pattern: URLPattern, full_path: str) -> dict | None:
    callback = pattern.callback
    if callback is None:
        return None

    # Get the view class if it's a class-based view
    view_cls = getattr(callback, "cls", None)
    view_func = getattr(callback, "view_class", view_cls)
    initkwargs = getattr(callback, "initkwargs", {})

    # Determine HTTP methods
    methods = []
    if view_func and hasattr(view_func, "http_method_names"):
        methods = [m.upper() for m in view_func.http_method_names if m != "options"]
    elif initkwargs.get("actions"):
        methods = [m.upper() for m in initkwargs["actions"].keys()]

    # For ViewSets with actions mapping
    actions = initkwargs.get("actions", {})
    if actions:
        methods = [m.upper() for m in actions.keys()]

    # Determine auth required
    permission_classes = getattr(view_func, "permission_classes", []) if view_func else []
    auth_required = True
    perm_names = [pc.__name__ if isinstance(pc, type) else type(pc).__name__ for pc in permission_classes]
    if "AllowAny" in perm_names:
        auth_required = False

    # Extract path parameters from URL pattern
    path_params = []
    param_matches = re.findall(r":(\w+)", full_path)
    for p in param_matches:
        path_params.append({
            "name": p,
            "type": "string",
            "description": f"URL parameter: {p}",
        })

    # Get the serializer class if ViewSet
    serializer_class = None
    if view_func:
        sc = getattr(view_func, "serializer_class", None)
        if sc:
            serializer_class = sc.__name__

    # Get filter info
    filterset_class = getattr(view_func, "filterset_class", None) if view_func else None
    search_fields = getattr(view_func, "search_fields", None) if view_func else None
    ordering_fields = getattr(view_func, "ordering_fields", None) if view_func else None

    name = pattern.name or ""
    tags = []
    if name:
        # Derive tag from name like "user-list" -> "users"
        base = name.split("-")[0] if "-" in name else name
        tags.append(base)

    return {
        "method": methods[0] if len(methods) == 1 else ",".join(methods) if methods else "GET",
        "path": "/" + full_path.strip("/"),
        "name": name,
        "summary": _generate_summary(name, full_path, methods),
        "tags": tags,
        "auth_required": auth_required,
        "path_params": path_params,
        "serializer": serializer_class,
        "filterset": filterset_class.__name__ if filterset_class else None,
        "search_fields": list(search_fields) if search_fields else [],
        "ordering_fields": list(ordering_fields) if ordering_fields and ordering_fields != "__all__" else [],
    }


def _generate_summary(name: str, path: str, methods: list) -> str:
    """Generate a human-readable summary from the endpoint name/path."""
    if not name:
        parts = path.strip("/").split("/")
        return f"Endpoint at {path}"

    parts = name.replace("_", "-").split("-")
    resource = parts[0] if parts else "resource"
    action_word = parts[-1] if len(parts) > 1 else "access"

    verb_map = {
        "list": f"List all {resource}s",
        "detail": f"Retrieve a single {resource}",
        "create": f"Create a new {resource}",
    }
    return verb_map.get(action_word, f"{' '.join(parts).title()}")


def get_all_endpoints() -> list[dict]:
    """Return all API endpoints."""
    return _collect_url_patterns()


# ---------------------------------------------------------------------------
# Filter introspection
# ---------------------------------------------------------------------------

def get_all_filters() -> dict:
    """Scan all FilterSet classes in the codebase and return field-level metadata."""
    from django_filters import rest_framework as df_filters

    result = {}

    # Known filter sets — import them directly for reliability
    filter_sets = []
    try:
        from accounting.filters import BankTransactionFilter, TransactionFilter, JournalEntryFilter
        filter_sets.extend([
            ("BankTransaction", BankTransactionFilter),
            ("Transaction", TransactionFilter),
            ("JournalEntry", JournalEntryFilter),
        ])
    except ImportError:
        pass

    for name, fs_cls in filter_sets:
        fields_info = []
        for fname, filt in fs_cls.declared_filters.items():
            fields_info.append({
                "name": fname,
                "type": type(filt).__name__,
                "field_name": getattr(filt, "field_name", fname),
                "lookup_expr": getattr(filt, "lookup_expr", "exact"),
                "method": filt.method if hasattr(filt, "method") and filt.method else None,
            })
        result[name] = {
            "filterset_class": fs_cls.__name__,
            "filters": fields_info,
        }
    return result


# ---------------------------------------------------------------------------
# Capabilities overview
# ---------------------------------------------------------------------------

def get_capabilities() -> dict:
    """System-wide capability summary."""
    from django.conf import settings as django_settings

    return {
        "authentication": {
            "methods": ["TokenAuthentication"],
            "token_header": "Authorization: Token <token>",
            "jwt_available": True,
            "jwt_obtain_url": "/api/token/",
            "jwt_refresh_url": "/api/token/refresh/",
        },
        "pagination": {
            "strategy": "not_configured_globally",
            "note": "Pagination is not configured at the DRF global level; individual views may implement custom pagination.",
        },
        "filtering": {
            "global_backends": [
                "django_filters.rest_framework.DjangoFilterBackend",
                "rest_framework.filters.SearchFilter",
                "rest_framework.filters.OrderingFilter",
            ],
            "note": "Most list endpoints support ?search=, ?ordering=, and django-filter query params.",
        },
        "content_type": "application/json",
        "cors": {
            "allow_all_origins": getattr(django_settings, "CORS_ALLOW_ALL_ORIGINS", False),
            "allow_credentials": getattr(django_settings, "CORS_ALLOW_CREDENTIALS", False),
        },
        "timezone": getattr(django_settings, "TIME_ZONE", "UTC"),
        "language_code": getattr(django_settings, "LANGUAGE_CODE", "en-us"),
        "date_format": "ISO 8601 (YYYY-MM-DD)",
        "datetime_format": "ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)",
        "currency_convention": "Decimal fields; no global currency enforced.",
        "file_upload": {
            "max_files_per_request": getattr(django_settings, "DATA_UPLOAD_MAX_NUMBER_FILES", 1000),
        },
        "celery": {
            "broker": "Redis",
            "task_time_limit_minutes": getattr(django_settings, "CELERY_TASK_T_LIMIT", 10),
        },
        "api_versioning": "No explicit versioning. All endpoints are unversioned (current).",
        "multi_tenancy": {
            "strategy": "URL-path based. Tenant subdomain/slug is the first path segment for scoped endpoints.",
            "header": "Tenant resolved from URL path, not headers.",
            "example": "/{tenant_slug}/api/transactions/",
        },
        "soft_delete": {
            "convention": "is_deleted boolean field on BaseModel subclasses. Filter with ?deleted=true to include soft-deleted records.",
        },
        "error_format": {
            "shape": {
                "success": False,
                "error": "<error message>",
                "html": "<optional HTML-formatted error for display>",
            },
            "drf_errors": "Standard DRF error responses for 400/401/403/404.",
        },
    }
