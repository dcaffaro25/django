from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, DEFAULT_DB_ALIAS, models


# System apps we usually don't include when you say "my tables"
DEFAULT_EXCLUDED_APPS = {"contenttypes", "admin", "sessions", "django_celery_results"}

def app_tables(include_system: bool) -> Tuple[set, Dict[str, str]]:
    """
    Returns:
      - a set of table names we consider 'user tables'
      - a mapping table_name -> "app_label.ModelName" for pretty printing
    """
    tables: set = set()
    pretty: Dict[str, str] = {}

    for m in apps.get_models():
        app_label = m._meta.app_label
        if not include_system and app_label in DEFAULT_EXCLUDED_APPS:
            continue
        if not m._meta.managed:
            continue

        # main model table
        tables.add(m._meta.db_table)
        pretty[m._meta.db_table] = f"{app_label}.{m.__name__}"

        # auto-created M2M tables
        for m2m in m._meta.many_to_many:
            through = m2m.remote_field.through
            if getattr(through._meta, "auto_created", False):
                tables.add(through._meta.db_table)
                pretty[through._meta.db_table] = f"{app_label}.{m.__name__} (m2m:{m2m.name})"

    return tables, pretty


def safe_count(alias: str, table: str) -> int | None:
    """
    SELECT COUNT(*) on a table for a DB alias.
    Returns None if the table doesn't exist on that alias.
    """
    if alias not in connections.databases:
        raise CommandError(f"Database alias '{alias}' is not configured.")

    conn = connections[alias]
    qname = conn.ops.quote_name(table)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {qname}")
            return int(cur.fetchone()[0])
    except Exception:
        # Missing table or other issue – treat as absent for that alias
        return None


class Command(BaseCommand):
    help = "Show how many tables and how many rows per table in one or more DB aliases (default + old)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aliases",
            nargs="+",
            default=[DEFAULT_DB_ALIAS, "old"],
            help="DB aliases to inspect (default: 'default old').",
        )
        parser.add_argument(
            "--include-system",
            action="store_true",
            help="Include Django system apps (admin, contenttypes, sessions, django_celery_results).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output as JSON instead of pretty text.",
        )

    def handle(self, *args, **opts):
        aliases: List[str] = opts["aliases"]
        include_system: bool = opts["include_system"]
        as_json: bool = opts["json"]

        # Validate aliases up-front
        for a in aliases:
            if a not in connections.databases:
                raise CommandError(f"Database alias '{a}' is not configured in settings.DATABASES.")

        tables, pretty = app_tables(include_system=include_system)
        if not tables:
            self.stdout.write(self.style.WARNING("No tables found to inspect."))
            return

        # Gather counts
        results = defaultdict(dict)  # table -> alias -> count
        totals_by_alias = defaultdict(int)

        for table in sorted(tables):
            for alias in aliases:
                cnt = safe_count(alias, table)
                results[table][alias] = cnt
                if isinstance(cnt, int):
                    totals_by_alias[alias] += cnt

        # Sort tables by the first alias's count (desc), falling back to name
        primary = aliases[0]
        table_order = sorted(
            tables,
            key=lambda t: (-(results[t].get(primary) or -1), t),
        )

        if as_json:
            payload = {
                "aliases": aliases,
                "tables": [
                    {
                        "table": t,
                        "model": pretty.get(t),
                        "counts": {a: results[t].get(a) for a in aliases},
                    }
                    for t in table_order
                ],
                "summary": {
                    "table_count": len(tables),
                    "row_totals": dict(totals_by_alias),
                },
            }
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=False))
            return

        # Pretty text output
        self.stdout.write(self.style.MIGRATE_HEADING("Database table counts"))
        self.stdout.write(f"Aliases: {', '.join(aliases)}")
        self.stdout.write(f"Including system apps: {'yes' if include_system else 'no'}")
        self.stdout.write("")

        # Header
        header_cols = ["table", "model/name"] + [f"rows@{a}" for a in aliases]
        self.stdout.write(" | ".join(f"{h:<40}" if i < 2 else f"{h:>12}" for i, h in enumerate(header_cols)))
        self.stdout.write("-" * (40 + 3 + 40 + 3 + len(aliases) * (12 + 3)))

        for t in table_order:
            row = [
                f"{t:<40}",
                f"{(pretty.get(t) or '-'): <40}",
            ]
            for a in aliases:
                val = results[t].get(a)
                row.append(f"{(val if val is not None else '-'):>12}")
            self.stdout.write(" | ".join(row))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_LABEL(f"Tables inspected: {len(tables)}"))
        for a in aliases:
            self.stdout.write(self.style.SUCCESS(f"Total rows @ {a}: {totals_by_alias.get(a, 0)}"))
