# core/management/commands/copy_all_from_old.py
from __future__ import annotations
from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import connections, transaction
from django.db.models import ForeignKey, ManyToManyField, Model
from pgvector.django import VectorField

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

# Apps / models we don't want to copy (Django system tables; they are (re)created by migrate)
EXCLUDED_APPS = {
    "contenttypes",
    "admin",
    "sessions",
    "django_celery_results",
}
EXCLUDED_MODELS = {
    "auth.Permission",        # permissions are regenerated
    "admin.LogEntry",
    "sessions.Session",
}

DEFAULT_CHUNK = 1000

def model_key(m: Model) -> str:
    return f"{m._meta.app_label}.{m.__name__}"

def existing_columns(using_alias: str, table_name: str) -> Set[str]:
    with connections[using_alias].cursor() as cur:
        cols = connections[using_alias].introspection.get_table_description(cur, table_name)
        return {c.name for c in cols}

def is_mptt_model(model: type[Model]) -> bool:
    # heuristic: MPTT adds level/lft/rght/tree_id fields
    names = {f.name for f in model._meta.get_fields()}
    return {"level", "lft", "rght"}.issubset(names)

def copyable_concrete_field_names(model: type[Model], old_cols: Set[str]) -> List[str]:
    """
    Concrete fields to copy from OLD -> NEW:
    - keep PK explicitly
    - skip VectorField (new in code but not in old DB)
    - include only fields whose column exists in OLD
    """
    names = []
    for f in model._meta.concrete_fields:
        if f.primary_key:
            names.append(f.attname)  # usually 'id'
            continue
        if isinstance(f, VectorField):
            continue
        if f.column in old_cols:
            names.append(f.attname)  # FK uses '<name>_id'
    return names

def build_model_list(app_labels: List[str]) -> List[type[Model]]:
    models = []
    for app_label in app_labels:
        if app_label in EXCLUDED_APPS:
            continue
        for m in apps.get_app_config(app_label).get_models():
            if model_key(m) in EXCLUDED_MODELS:
                continue
            # only concrete, managed models
            if not m._meta.managed or m._meta.proxy:
                continue
            models.append(m)
    return models

def topo_sort_models(models: List[type[Model]]) -> List[type[Model]]:
    """
    Topologically sort models by FK dependencies so parents come before children.
    Self-FKs (e.g., MPTT) are ignored here (handled via per-model ordering).
    """
    key_to_model = {model_key(m): m for m in models}
    indeg = defaultdict(int)
    edges: Dict[str, Set[str]] = defaultdict(set)

    for m in models:
        mk = model_key(m)
        indeg.setdefault(mk, 0)
        for f in m._meta.get_fields():
            if isinstance(f, ForeignKey):
                other = f.remote_field.model
                if not isinstance(other, type) or not issubclass(other, Model):
                    continue
                ok = model_key(other)
                if ok == mk:
                    # self-FK: handled by per-row ordering later
                    continue
                if ok in key_to_model:
                    if mk not in edges[ok]:
                        edges[ok].add(mk)
                        indeg[mk] += 1

    q = deque([k for k in indeg if indeg[k] == 0])
    ordered_keys = []
    while q:
        k = q.popleft()
        ordered_keys.append(k)
        for v in edges.get(k, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    # fall back (in case of cy
