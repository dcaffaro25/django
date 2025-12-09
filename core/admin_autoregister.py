# core/admin_autoregister.py
from __future__ import annotations

from django.apps import apps
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered
from django.contrib.admin import SimpleListFilter
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

class NotesFilter(SimpleListFilter):
    """
    Custom filter for notes field: Has Notes / No Notes
    """
    title = 'notes'
    parameter_name = 'notes'

    def lookups(self, request, model_admin):
        return (
            ('has_notes', 'Has Notes'),
            ('no_notes', 'No Notes'),
        )

    def queryset(self, request, queryset):
        from django.db.models import Q
        if self.value() == 'has_notes':
            return queryset.exclude(notes__isnull=True).exclude(notes='')
        elif self.value() == 'no_notes':
            return queryset.filter(Q(notes__isnull=True) | Q(notes=''))
        return queryset

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
    Always includes 'notes' if the model has it.
    """
    names: list[str] = []
    pk_name = model._meta.pk.attname or model._meta.pk.name
    names.append(pk_name)
    
    # Check if model has notes field - we'll add it at the end
    has_notes = 'notes' in [f.name for f in model._meta.get_fields()]

    for f in model._meta.get_fields():
        if not getattr(f, "concrete", False):
            continue
        name = getattr(f, "attname", f.name)
        if name == pk_name or name == 'notes':  # Skip notes here, add it at the end
            continue
        names.append(name)
        if len(names) >= MAX_LIST_DISPLAY_FIELDS - (1 if has_notes else 0):
            break
    
    # Add notes at the end if the model has it
    if has_notes and 'notes' not in names:
        names.append('notes')

    # Fallback: ensure at least pk appears
    return names or [pk_name]

def pick_search_fields(model) -> list[str]:
    """
    Prefer common naming conventions; otherwise all Char/Text fields.
    Always includes 'notes' if the model has it.
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
    
    # Always add notes to search if the model has it
    if 'notes' in field_names and 'notes' not in fields:
        fields.append('notes')

    # Dedup, cap to something reasonable
    seen = set()
    uniq = []
    for s in fields:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:8] or [model._meta.pk.attname]

def pick_list_filters(model) -> list:
    """
    Booleans, choices, dates, and small FKs become sidebar filters.
    Always includes a custom notes filter if the model has it.
    """
    filters: list = []
    has_notes = False
    
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
        elif f.name == 'notes':
            has_notes = True
    
    # Add custom notes filter if model has notes field
    if has_notes:
        filters.append(NotesFilter)
    
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
    
    # Check if model has notes field to add custom form
    has_notes = 'notes' in [f.name for f in model._meta.get_fields()]

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
    
    # Add notes field to form if model has it (with better widget)
    if has_notes:
        # Create a custom admin form that includes notes with a better widget
        from django import forms
        from django.contrib.admin.widgets import AdminTextareaWidget
        
        # Create form class dynamically
        form_class_name = f"{model.__name__}AdminForm"
        form_meta = type('Meta', (), {
            'model': model,
            'fields': '__all__',
            'widgets': {
                'notes': AdminTextareaWidget(attrs={'rows': 4, 'cols': 80}),
            }
        })
        NotesModelForm = type(form_class_name, (forms.ModelForm,), {'Meta': form_meta})
        
        attrs['form'] = NotesModelForm
    
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
