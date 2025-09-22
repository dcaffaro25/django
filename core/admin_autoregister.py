# core/admin_autoregister.py
from __future__ import annotations

from django.apps import apps
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from django.db import models
from typing import Iterable

# ---- Customize these if needed ----
EXCLUDE_APPS: set[str] = {
    "contenttypes", "sessions", "admin", "auth",
}
EXCLUDE_MODELS: set[str] = {
    # e.g. "YourApp.YourModel",
}
MAX_LIST_DISPLAY_FIELDS = 10  # pk + first N fields
SMALL_FK_LIMIT = 500         # only offer list_filter for FKs with <= this many rows
# -----------------------------------

def is_small_fk(field: models.Field) -> bool:
    try:
        rel_model = field.remote_field.model
        if rel_model is None:
            return False
        return rel_model._default_manager.count() <= SMALL_FK_LIMIT
    except Exception:
        return False

def pick_list_display_fields(model) -> list[str]:
    """
    pk + first few concrete fields that are not too verbose.
    Django automatically makes DB fields sortable in the changelist.
    """
    names: list[str] = []
    pk_name = model._meta.pk.attname or model._meta.pk.name
    names.append(pk_name)

    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        name = getattr(f, "attname", f.name)
        if name == pk_name:
            continue
        names.append(name)
        if len(names) >= MAX_LIST_DISPLAY_FIELDS:
            break

    # Fallback: ensure at least pk appears
    return names or [pk_name]

def pick_search_fields(model) -> list[str]:
    """
    Prefer common naming conventions; otherwise all Char/Text fields.
    """
    preferred = ("name", "title", "code", "description", "email", "slug")
    fields = []
    field_names = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
    for cand in preferred:
        if cand in field_names:
            fields.append(cand)

    if not fields:
        for f in model._meta.get_fields():
            if isinstance(f, (models.CharField, models.TextField)):
                fields.append(f.name)

    # Use related lookups for FKs with obvious names
    for f in model._meta.get_fields():
        if isinstance(f, models.ForeignKey):
            if "name" in {ff.name for ff in f.related_model._meta.get_fields()}:
                fields.append(f"{f.name}__name")

    # Dedup, cap to something reasonable
    seen = set()
    uniq = []
    for s in fields:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:8] or [model._meta.pk.attname]

def pick_list_filters(model) -> list[str]:
    """
    Booleans, choices, dates, and small FKs become sidebar filters.
    """
    filters: list[str] = []
    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        if isinstance(f, (models.BooleanField,)):
            filters.append(f.name)
        elif getattr(f, "choices", None):
            filters.append(f.name)
        elif isinstance(f, (models.DateField, models.DateTimeField)):
            filters.append(f.name)
        elif isinstance(f, models.ForeignKey) and is_small_fk(f):
            filters.append(f.name)
    return filters[:6]

def pick_select_related(model) -> list[str]:
    """Follow FK columns to reduce N+1 on list views."""
    fks = []
    for f in model._meta.get_fields():
        if isinstance(f, models.ForeignKey):
            fks.append(f.name)
    return fks

def should_skip_model(model) -> bool:
    app_label = model._meta.app_label
    full_name = f"{app_label}.{model.__name__}"
    return (app_label in EXCLUDE_APPS) or (full_name in EXCLUDE_MODELS)

def make_admin_for_model(model):
    list_display = pick_list_display_fields(model)
    list_filter = pick_list_filters(model)
    search_fields = pick_search_fields(model)
    select_related = pick_select_related(model)

    # Build a dynamic ModelAdmin subclass with static attributes
    attrs = dict(
        list_display=tuple(list_display),
        list_filter=tuple(list_filter),
        search_fields=tuple(search_fields),
        list_select_related=tuple(select_related),
        ordering=("-%s" % list_display[0],),  # default: newest/desc by pk (or first field)
        list_per_page=50,
        date_hierarchy=None,   # you can set to a date field name if present
        autocomplete_fields=(),  # you may enable for very large FKs if you want
        save_on_top=True,
    )
    return type(f"Dynamic{model.__name__}Admin", (admin.ModelAdmin,), attrs)

def auto_register_all_models():
    for model in apps.get_models():
        if should_skip_model(model):
            continue
        try:
            admin.site.register(model, make_admin_for_model(model))
        except AlreadyRegistered:
            # Respect any hand-crafted admin a developer already registered
            continue

# Call this at import time (safe), or from AppConfig.ready()
auto_register_all_models()
