# -*- coding: utf-8 -*-
"""
Bootstrap a 1-level ProductServiceCategory tree for one or all tenants
by clustering products by their first content token.

Examples:
    python manage.py bootstrap_product_families --tenant evolat --dry-run
    python manage.py bootstrap_product_families --tenant evolat --min-cluster 8
    python manage.py bootstrap_product_families --all-tenants
    python manage.py bootstrap_product_families --tenant evolat --overwrite

The bootstrap is idempotent: re-running won't move products that
already have a category (unless --overwrite is passed) and won't
recreate categories with the same name. Safe to use as a periodic
hygiene pass after large product imports.
"""
from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Induce a starter ProductServiceCategory tree from product "
        "names. Clusters by first content token; categories with "
        "fewer than --min-cluster products are skipped."
    )

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--tenant", help="Subdomain of the tenant.")
        scope.add_argument(
            "--all-tenants",
            action="store_true",
            help="Run for every tenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Wrap writes in a savepoint that rolls back at the end.",
        )
        parser.add_argument(
            "--min-cluster",
            type=int,
            default=5,
            help="Minimum products per cluster to create a category.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help=(
                "Re-assign products that already have a category. "
                "Default behavior preserves operator-curated assignments."
            ),
        )

    def handle(self, *args, **opts):
        from billing.services.ps_family_service import bootstrap_family_tree

        if opts["all_tenants"]:
            companies = list(Company.objects.all())
        else:
            try:
                companies = [Company.objects.get(subdomain=opts["tenant"])]
            except Company.DoesNotExist as e:
                raise CommandError(f"Tenant '{opts['tenant']}' not found.") from e

        for company in companies:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n=== Tenant {company.subdomain} (id={company.id}) ==="
            ))
            try:
                stats = bootstrap_family_tree(
                    company,
                    min_cluster=opts["min_cluster"],
                    overwrite_existing=opts["overwrite"],
                    dry_run=opts["dry_run"],
                )
                samples = stats.pop("sample_clusters", [])
                for k, v in stats.items():
                    self.stdout.write(f"  {k}: {v}")
                if samples:
                    self.stdout.write("  sample_clusters:")
                    for token, count, names in samples:
                        self.stdout.write(f"    [{count:3d}] {token!r}")
                        for n in names:
                            self.stdout.write(f"         {n!r}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  FAILED for {company.subdomain}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS("\nDone."))
