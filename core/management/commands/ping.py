# core/management/commands/copy_all_from_old.py
from __future__ import annotations
from django.core.management.color import no_style
from collections import defaultdict
from io import StringIO
from typing import Dict, List, Set

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import connections, transaction
from django.db.models import ForeignKey, Model

try:
    from pgvector.django import VectorField
except Exception:
    class VectorField:
        pass

EXCLUDED_APPS = {"contenttypes", "admin", "sessions", "django_celery_results"}
EXCLUDED_MODELS = {"auth.Permission", "admin.LogEntry", "sessions.Session"}
DEFAULT_CHUNK = 1000


def mkey(m: type[Model]) -> str:
    return f"{m._meta.app_label}.{m.__name__}"


def existing_columns(alias: str, table: str) -> Set[str]:
    with connections[alias].cursor() as cur:
        desc = connections[alias].introspection.get_table_description(cur, table)
        return {c.name for c in desc}


def is_mptt(model: type[Model]) -> bool:
    names = {f.name for f in model._meta.get_fields()}
    return {"level", "lft", "rght"}.issubset(names)


def copyable_fields(model: type[Model], old_cols: Set[str]) -> List[str]:
    names: List[str] = []
    for f in model._meta.concrete_fields:
        if f.primary_key:
            names.append(f.attname)
            continue
        if isinstance(f, VectorField):
            continue
        if f.column in old_cols:
            names.append(f.attname)
    return names


def collect_models(app_labels: List[str]) -> List[type[Model]]:
    models: List[type[Model]] = []
    for label in app_labels:
        if label in EXCLUDED_APPS:
            continue
        for m in apps.get_app_config(label).get_models():
            if mkey(m) in EXCLUDED_MODELS:
                continue
            if not m._meta.managed or m._meta.proxy:
                continue
            models.append(m)
    return models


def topo_sort(models: List[type[Model]]) -> List[type[Model]]:
    key2model = {mkey(m): m for m in models}
    indeg = defaultdict(int)
    edges: Dict[str, Set[str]] = defaultdict(set)

    for m in models:
        mk = mkey(m)
        indeg.setdefault(mk, 0)
        for f in m._meta.get_fields():
            if isinstance(f, ForeignKey):
                other = f.remote_field.model
                if not isinstance(other, type) or not issubclass(other, Model):
                    continue
                ok = mkey(other)
                if ok == mk:
                    continue
                if ok in key2model and mk not in edges[ok]:
                    edges[ok].add(mk)
                    indeg[mk] += 1

    from collections import deque
    q = deque([k for k in indeg if indeg[k] == 0])
    order: List[str] = []
    while q:
        k = q.popleft()
        order.append(k)
        for v in edges.get(k, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    if len(order) != len(indeg):
        remaining = [k for k in indeg if k not in order]
        order += sorted(remaining)

    return [key2model[k] for k in order]


def run_sql_blob_safely(sql_blob: str, using_alias: str) -> None:
    """
    Execute a multi-statement SQL blob safely: strip comments, split on semicolons,
    skip BEGIN/COMMIT, and run each statement individually.
    """
    # Strip line comments
    lines = []
    for ln in sql_blob.splitlines():
        stripped = ln.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(ln)
    joined = "\n".join(lines)

    # Split on semicolons and execute one by one
    for part in joined.split(";"):
        stmt = part.strip()
        if not stmt:
            continue
        up = stmt.upper()
        if up in ("BEGIN", "COMMIT"):
            continue
        with connections[using_alias].cursor() as cur:
            cur.execute(stmt)


class Command(BaseCommand):
    help = "Copy all data from the 'old' DB alias to the 'default' DB, preserving IDs (and M2M)."

    def add_arguments(self, parser):
        parser.add_argument("--apps", nargs="*", default=None)
        parser.add_argument("--chunk", type=int, default=DEFAULT_CHUNK)
        parser.add_argument("--wipe-target", action="store_true")
        parser.add_argument("--skip-existing", action="store_true")

    def handle(self, *args, **opts):
        old = "old"
        new = "default"
        if old not in connections.databases:
            raise CommandError("DATABASES must include an 'old' alias.")
        if new not in connections.databases:
            raise CommandError("DATABASES must include a 'default' alias (target).")

        app_labels = opts["apps"] or [c.label for c in apps.get_app_configs() if c.label not in EXCLUDED_APPS]
        models = collect_models(app_labels)
        models_sorted = topo_sort(models)
        models_by_key = {mkey(m): m for m in models}

        if not (opts["wipe_target"] or opts["skip_existing"]):
            for m in models_sorted:
                if m.objects.using(new).exists():
                    raise CommandError(
                        f"Target DB '{new}' is not empty (first data seen in {mkey(m)}). "
                        f"Re-run with --wipe-target or --skip-existing."
                    )

        if opts["wipe_target"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Wiping target DB (reverse FK order)…"))
            with transaction.atomic(using=new):
                for m in reversed(models_sorted):
                    cnt = m.objects.using(new).count()
                    if cnt:
                        m.objects.using(new).all().delete()
                        self.stdout.write(f"[wipe] {mkey(m)}: deleted {cnt} rows")
            self.stdout.write(self.style.SUCCESS("Target wiped."))

        self.stdout.write(self.style.MIGRATE_HEADING("Copying base rows (FK-safe order)…"))
        with transaction.atomic(using=new):
            for m in models_sorted:
                table = m._meta.db_table
                old_cols = existing_columns(old, table)
                fields = copyable_fields(m, old_cols)
                if not fields:
                    self.stdout.write(self.style.WARNING(f"[skip] {mkey(m)} (no copyable fields)"))
                    continue

                pk_name = m._meta.pk.attname
                qs = m.objects.using(old).all()
                if is_mptt(m) and "level" in old_cols:
                    qs = qs.order_by("level", pk_name)
                else:
                    qs = qs.order_by(pk_name)

                total = qs.count()
                if total == 0:
                    self.stdout.write(f"[ok] {mkey(m)}: 0 rows")
                    continue

                batch_size = int(opts["chunk"])
                to_create: List[Model] = []
                created = 0
                for row in qs.values(*fields).iterator(chunk_size=batch_size):
                    to_create.append(m(**row))
                    if len(to_create) >= batch_size:
                        m.objects.using(new).bulk_create(
                            to_create, batch_size=batch_size, ignore_conflicts=opts["skip_existing"]
                        )
                        created += len(to_create)
                        to_create.clear()
                if to_create:
                    m.objects.using(new).bulk_create(
                        to_create, batch_size=batch_size, ignore_conflicts=opts["skip_existing"]
                    )
                    created += len(to_create)
                self.stdout.write(self.style.SUCCESS(f"[ok] {mkey(m)}: copied {created}/{total}"))

        self.stdout.write(self.style.MIGRATE_HEADING("Rebuilding ManyToMany links…"))
        with transaction.atomic(using=new):
            for m in models_sorted:
                for m2m in m._meta.many_to_many:
                    rel_name = m2m.name
                    target = m2m.remote_field.model
                    if mkey(target) not in models_by_key:
                        continue
                    local_pk = m._meta.pk.attname
                    remote_pk = target._meta.pk.attname

                    qs_old = m.objects.using(old).only(local_pk).order_by(local_pk)
                    cnt = qs_old.count()
                    done = 0
                    for old_obj in qs_old.iterator(chunk_size=DEFAULT_CHUNK):
                        try:
                            new_obj = m.objects.using(new).get(pk=getattr(old_obj, local_pk))
                        except m.DoesNotExist:
                            continue
                        rel_ids = list(getattr(old_obj, rel_name).all().values_list(remote_pk, flat=True))
                        if rel_ids:
                            getattr(new_obj, rel_name).set(rel_ids)
                        done += 1
                    self.stdout.write(self.style.SUCCESS(f"[ok] {mkey(m)}.{rel_name}: linked for {done}/{cnt}"))

        # ===== FIXED: run sequencereset SQL safely =====
        # Resetting sequences…
        self.stdout.write(self.style.MIGRATE_HEADING("Resetting sequences…"))
        
        # Build a list of models per app label we actually copied
        app_to_models = {label: [] for label in app_labels}
        for m in models_sorted:
            lbl = m._meta.app_label
            if lbl in app_to_models:
                app_to_models[lbl].append(m)
        
        for app_label, model_list in app_to_models.items():
            if not model_list:
                continue
            # Ask the backend for per-model reset SQL (no BEGIN/COMMIT)
            sql_list = connections[new].ops.sequence_reset_sql(no_style(), model_list)
            if not sql_list:
                continue
            with connections[new].cursor() as cur:
                for stmt in sql_list:
                    cur.execute(stmt)
            self.stdout.write(self.style.SUCCESS(f"[ok] sequences reset: {app_label}"))
        
        self.stdout.write(self.style.SUCCESS("✅ All done. IDs preserved; M2M rebuilt; sequences reset."))
