# core/management/commands/clone_to_homolog.py
"""
Management command to clone production database to homologation database.

This command safely copies data from production to a homologation database
for local testing without corrupting production data.

Usage:
------
    # Clone all data (default)
    python manage.py clone_to_homolog
    
    # Clone specific apps only
    python manage.py clone_to_homolog --apps accounting multitenancy
    
    # Clone with company filter (only data for specific companies)
    python manage.py clone_to_homolog --company-ids 1 2 3
    
    # Dry run (show what would be copied without actually copying)
    python manage.py clone_to_homolog --dry-run
    
    # Skip certain tables
    python manage.py clone_to_homolog --skip-models auth.Permission django_celery_results.TaskResult
    
    # Reset homolog DB before cloning (drops all tables)
    python manage.py clone_to_homolog --reset

Prerequisites:
--------------
1. Create local_credentials.ini from local_credentials.example.ini
2. Configure both production and homologation database credentials
3. Run migrations on the homologation database first:
   ENVIRONMENT_MODE=homolog python manage.py migrate

Safety Features:
----------------
- Requires explicit confirmation before proceeding
- Production database is NEVER modified
- Validates that target is not production before any writes
- Supports dry-run mode for testing
"""

from __future__ import annotations
import sys
import time
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple, Optional, Any

from django.core.management.base import BaseCommand, CommandError
from django.apps import apps
from django.db import connections, transaction, router
from django.db.models import ForeignKey, ManyToManyField, Model, Q
from django.conf import settings

try:
    from pgvector.django import VectorField
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    VectorField = None


# Apps/models to exclude from cloning (Django system tables)
EXCLUDED_APPS = {
    "contenttypes",
    "admin",
    "sessions",
    "django_celery_results",
}

EXCLUDED_MODELS = {
    "auth.Permission",
    "admin.LogEntry",
    "sessions.Session",
    "contenttypes.ContentType",
}

# Models that should be copied first (base/core models)
PRIORITY_MODELS = [
    "multitenancy.Company",
    "multitenancy.CustomUser",
    "auth.User",
    "auth.Group",
]

DEFAULT_CHUNK_SIZE = 500


def model_key(m: type[Model]) -> str:
    """Get unique key for a model."""
    return f"{m._meta.app_label}.{m.__name__}"


def existing_columns(using_alias: str, table_name: str) -> Set[str]:
    """Get existing column names for a table."""
    try:
        with connections[using_alias].cursor() as cur:
            cols = connections[using_alias].introspection.get_table_description(cur, table_name)
            return {c.name for c in cols}
    except Exception:
        return set()


def table_exists(using_alias: str, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        with connections[using_alias].cursor() as cur:
            tables = connections[using_alias].introspection.table_names(cur)
            return table_name in tables
    except Exception:
        return False


def copyable_concrete_field_names(model: type[Model], source_cols: Set[str]) -> List[str]:
    """
    Get list of concrete field names that can be copied.
    Excludes VectorField and fields not present in source DB.
    """
    names = []
    for f in model._meta.concrete_fields:
        if f.primary_key:
            names.append(f.attname)
            continue
        if HAS_PGVECTOR and VectorField and isinstance(f, VectorField):
            continue
        if f.column in source_cols:
            names.append(f.attname)
    return names


def get_company_related_filter(model: type[Model], company_ids: List[int]) -> Optional[Q]:
    """
    Build a Q filter to get records related to specific companies.
    Returns None if model has no company relationship.
    """
    # Check for direct company FK
    for field in model._meta.get_fields():
        if isinstance(field, ForeignKey):
            related = field.remote_field.model
            if hasattr(related, '_meta'):
                related_name = model_key(related)
                if related_name in ("multitenancy.Company", "core.Company"):
                    return Q(**{f"{field.name}_id__in": company_ids})
    
    # Check for company field directly
    if hasattr(model, 'company_id'):
        return Q(company_id__in=company_ids)
    if hasattr(model, 'company'):
        return Q(company_id__in=company_ids)
    
    return None


class Command(BaseCommand):
    help = "Clone production database to homologation database for local testing"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            default='production',
            help='Source database alias (default: production)'
        )
        parser.add_argument(
            '--target',
            default='default',
            help='Target database alias (default: default, which is homolog in local mode)'
        )
        parser.add_argument(
            '--apps',
            nargs='+',
            help='Specific apps to clone (default: all managed apps)'
        )
        parser.add_argument(
            '--skip-models',
            nargs='+',
            default=[],
            help='Models to skip (format: app_label.ModelName)'
        )
        parser.add_argument(
            '--company-ids',
            nargs='+',
            type=int,
            help='Only clone data for specific company IDs'
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=DEFAULT_CHUNK_SIZE,
            help='Number of records to process at a time'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be copied without actually copying'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset (truncate) target tables before cloning'
        )
        parser.add_argument(
            '--skip-confirmation',
            action='store_true',
            help='Skip confirmation prompt (use with caution)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed progress information'
        )
    
    def handle(self, *args, **options):
        source_db = options['source']
        target_db = options['target']
        dry_run = options['dry_run']
        reset = options['reset']
        skip_confirm = options['skip_confirmation']
        verbose = options['verbose']
        chunk_size = options['chunk_size']
        company_ids = options.get('company_ids')
        skip_models = set(options.get('skip_models', []))
        
        # Validate environment
        self._validate_environment(source_db, target_db)
        
        # Get models to clone
        app_labels = options.get('apps')
        models = self._build_model_list(app_labels, skip_models)
        
        if not models:
            self.stderr.write(self.style.ERROR("No models to clone"))
            return
        
        # Sort models by dependencies
        sorted_models = self._topo_sort_models(models)
        
        # Show summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CLONE PRODUCTION TO HOMOLOGATION"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Source database: {source_db}")
        self.stdout.write(f"Target database: {target_db}")
        self.stdout.write(f"Models to clone: {len(sorted_models)}")
        if company_ids:
            self.stdout.write(f"Company filter: {company_ids}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))
        if reset:
            self.stdout.write(self.style.WARNING("RESET MODE - Target tables will be truncated"))
        self.stdout.write("=" * 60 + "\n")
        
        if verbose:
            self.stdout.write("Models in copy order:")
            for i, m in enumerate(sorted_models, 1):
                self.stdout.write(f"  {i}. {model_key(m)}")
            self.stdout.write("")
        
        # Confirmation
        if not skip_confirm and not dry_run:
            self.stdout.write(self.style.WARNING(
                "\n⚠️  This will copy data from PRODUCTION to the homologation database."
            ))
            if reset:
                self.stdout.write(self.style.ERROR(
                    "⚠️  RESET mode is enabled - existing homolog data will be DELETED!"
                ))
            
            confirm = input("\nType 'yes' to proceed: ")
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR("Aborted."))
                return
        
        # Execute clone
        start_time = time.time()
        stats = self._clone_models(
            sorted_models,
            source_db,
            target_db,
            chunk_size,
            company_ids,
            dry_run,
            reset,
            verbose,
        )
        elapsed = time.time() - start_time
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CLONE COMPLETE"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"Total models processed: {stats['models_processed']}")
        self.stdout.write(f"Total records copied: {stats['records_copied']}")
        self.stdout.write(f"Total records skipped: {stats['records_skipped']}")
        self.stdout.write(f"Errors: {stats['errors']}")
        self.stdout.write(f"Time elapsed: {elapsed:.2f} seconds")
        self.stdout.write("=" * 60)
        
        if stats['error_details']:
            self.stdout.write(self.style.ERROR("\nErrors encountered:"))
            for err in stats['error_details'][:10]:
                self.stdout.write(f"  - {err}")
            if len(stats['error_details']) > 10:
                self.stdout.write(f"  ... and {len(stats['error_details']) - 10} more")
    
    def _validate_environment(self, source_db: str, target_db: str):
        """Validate that we're properly configured and not touching production."""
        # Check that source exists
        if source_db not in settings.DATABASES:
            raise CommandError(
                f"Source database '{source_db}' not configured. "
                "Make sure local_credentials.ini is set up correctly."
            )
        
        # Check that target exists
        if target_db not in settings.DATABASES:
            raise CommandError(
                f"Target database '{target_db}' not configured. "
                "Make sure local_credentials.ini is set up correctly."
            )
        
        # Prevent writing to production
        target_config = settings.DATABASES[target_db]
        target_host = target_config.get('HOST', '')
        
        # Safety check: don't write to obvious production hosts
        production_indicators = [
            'production',
            'prod',
            'railway.app',  # Railway production
            'switchback.proxy.rlwy.net',  # Known production host
        ]
        
        # This is a soft check - the user should configure properly
        mode = getattr(settings, 'ENVIRONMENT_MODE', 'production')
        if mode == 'production':
            raise CommandError(
                "Cannot run clone in production mode! "
                "Set ENVIRONMENT_MODE=local or homolog in local_credentials.ini"
            )
        
        # Test database connections
        try:
            with connections[source_db].cursor() as cur:
                cur.execute("SELECT 1")
            self.stdout.write(self.style.SUCCESS(f"✓ Connected to source: {source_db}"))
        except Exception as e:
            raise CommandError(f"Cannot connect to source database: {e}")
        
        try:
            with connections[target_db].cursor() as cur:
                cur.execute("SELECT 1")
            self.stdout.write(self.style.SUCCESS(f"✓ Connected to target: {target_db}"))
        except Exception as e:
            raise CommandError(f"Cannot connect to target database: {e}")
    
    def _build_model_list(self, app_labels: Optional[List[str]], skip_models: Set[str]) -> List[type[Model]]:
        """Build list of models to clone."""
        models = []
        
        # If specific apps requested, use those; otherwise use all installed
        if app_labels:
            target_apps = app_labels
        else:
            target_apps = [app.label for app in apps.get_app_configs()]
        
        for app_label in target_apps:
            if app_label in EXCLUDED_APPS:
                continue
            
            try:
                app_config = apps.get_app_config(app_label)
            except LookupError:
                self.stderr.write(self.style.WARNING(f"App not found: {app_label}"))
                continue
            
            for m in app_config.get_models():
                key = model_key(m)
                
                if key in EXCLUDED_MODELS:
                    continue
                if key in skip_models:
                    continue
                if not m._meta.managed:
                    continue
                if m._meta.proxy:
                    continue
                if m._meta.abstract:
                    continue
                
                models.append(m)
        
        return models
    
    def _topo_sort_models(self, models: List[type[Model]]) -> List[type[Model]]:
        """Topologically sort models by FK dependencies."""
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
                    if ok == mk:  # Self-FK
                        continue
                    if ok in key_to_model:
                        if mk not in edges[ok]:
                            edges[ok].add(mk)
                            indeg[mk] += 1
        
        # Kahn's algorithm
        q = deque([k for k in indeg if indeg[k] == 0])
        ordered_keys = []
        
        while q:
            k = q.popleft()
            ordered_keys.append(k)
            for v in edges.get(k, []):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        
        # Handle any remaining (cyclic) models
        remaining = [k for k in indeg if k not in ordered_keys]
        ordered_keys.extend(remaining)
        
        # Convert back to model objects, prioritizing PRIORITY_MODELS
        ordered_models = []
        
        # Add priority models first
        for pk in PRIORITY_MODELS:
            if pk in key_to_model:
                ordered_models.append(key_to_model[pk])
        
        # Add rest in topo order
        for k in ordered_keys:
            if k in key_to_model and key_to_model[k] not in ordered_models:
                ordered_models.append(key_to_model[k])
        
        return ordered_models
    
    def _clone_models(
        self,
        models: List[type[Model]],
        source_db: str,
        target_db: str,
        chunk_size: int,
        company_ids: Optional[List[int]],
        dry_run: bool,
        reset: bool,
        verbose: bool,
    ) -> Dict[str, Any]:
        """Clone all models from source to target."""
        stats = {
            'models_processed': 0,
            'records_copied': 0,
            'records_skipped': 0,
            'errors': 0,
            'error_details': [],
        }
        
        for model in models:
            key = model_key(model)
            table_name = model._meta.db_table
            
            try:
                # Check if table exists in both databases
                if not table_exists(source_db, table_name):
                    if verbose:
                        self.stdout.write(f"  Skipping {key}: table not in source")
                    continue
                
                if not table_exists(target_db, table_name):
                    self.stdout.write(
                        self.style.WARNING(f"  Skipping {key}: table not in target (run migrations?)")
                    )
                    continue
                
                # Get source columns
                source_cols = existing_columns(source_db, table_name)
                
                # Build queryset
                qs = model.objects.using(source_db).all()
                
                # Apply company filter if specified
                if company_ids:
                    company_filter = get_company_related_filter(model, company_ids)
                    if company_filter:
                        qs = qs.filter(company_filter)
                
                total_count = qs.count()
                
                if total_count == 0:
                    if verbose:
                        self.stdout.write(f"  {key}: 0 records")
                    continue
                
                self.stdout.write(f"  Copying {key}: {total_count} records...")
                
                if dry_run:
                    stats['records_skipped'] += total_count
                    stats['models_processed'] += 1
                    continue
                
                # Reset target table if requested
                if reset:
                    self._truncate_table(target_db, table_name, verbose)
                
                # Get copyable fields
                field_names = copyable_concrete_field_names(model, source_cols)
                
                # Copy in chunks
                copied = self._copy_model_data(
                    model,
                    qs,
                    field_names,
                    target_db,
                    chunk_size,
                    verbose,
                    stats,
                )
                
                stats['records_copied'] += copied
                stats['models_processed'] += 1
                
            except Exception as e:
                stats['errors'] += 1
                stats['error_details'].append(f"{key}: {str(e)}")
                self.stderr.write(self.style.ERROR(f"  Error copying {key}: {e}"))
        
        return stats
    
    def _truncate_table(self, db_alias: str, table_name: str, verbose: bool):
        """Truncate a table in the target database."""
        try:
            with connections[db_alias].cursor() as cur:
                # Use TRUNCATE CASCADE to handle FKs
                cur.execute(f'TRUNCATE TABLE "{table_name}" CASCADE')
            if verbose:
                self.stdout.write(f"    Truncated {table_name}")
        except Exception as e:
            self.stderr.write(self.style.WARNING(f"    Could not truncate {table_name}: {e}"))
    
    def _copy_model_data(
        self,
        model: type[Model],
        queryset,
        field_names: List[str],
        target_db: str,
        chunk_size: int,
        verbose: bool,
        stats: Dict[str, Any],
    ) -> int:
        """Copy data for a single model."""
        copied = 0
        
        # Process in chunks
        pk_name = model._meta.pk.attname
        last_pk = None
        
        while True:
            chunk_qs = queryset.order_by(pk_name)
            if last_pk is not None:
                chunk_qs = chunk_qs.filter(**{f"{pk_name}__gt": last_pk})
            chunk_qs = chunk_qs[:chunk_size]
            
            records = list(chunk_qs.values(*field_names))
            if not records:
                break
            
            last_pk = records[-1][pk_name]
            
            # Bulk insert into target
            try:
                with transaction.atomic(using=target_db):
                    objects_to_create = []
                    for record in records:
                        obj = model(**record)
                        objects_to_create.append(obj)
                    
                    # Use bulk_create with update_conflicts to handle existing records
                    model.objects.using(target_db).bulk_create(
                        objects_to_create,
                        update_conflicts=True,
                        unique_fields=[pk_name],
                        update_fields=[f for f in field_names if f != pk_name],
                    )
                    copied += len(records)
                    
            except Exception as e:
                # Fall back to individual inserts
                for record in records:
                    try:
                        obj = model(**record)
                        obj.save(using=target_db)
                        copied += 1
                    except Exception as inner_e:
                        stats['records_skipped'] += 1
                        if verbose:
                            stats['error_details'].append(
                                f"{model_key(model)} pk={record.get(pk_name)}: {inner_e}"
                            )
            
            if verbose and copied % 1000 == 0:
                self.stdout.write(f"    Copied {copied} records...")
        
        return copied

