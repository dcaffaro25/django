# -*- coding: utf-8 -*-
"""
Run ProductService group auto-discovery for one or all tenants.

Examples:
    python manage.py suggest_product_groups --tenant evolat --dry-run
    python manage.py suggest_product_groups --tenant evolat
    python manage.py suggest_product_groups --all-tenants --skip-head
    python manage.py suggest_product_groups --tenant evolat --head-size 4
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Bucket ProductService rows by name and emit Group suggestions. "
        "Two passes: exact-name (auto-promotes) and head-token "
        "(suggests only)."
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
            help="Wrap the work in a savepoint and roll back at the end.",
        )
        parser.add_argument(
            "--skip-exact",
            action="store_true",
            help="Skip the exact-name pass.",
        )
        parser.add_argument(
            "--skip-head",
            action="store_true",
            help="Skip the head-token pass.",
        )
        parser.add_argument(
            "--head-size",
            type=int,
            default=3,
            help="Number of leading tokens to use for head-cluster keys.",
        )

    def handle(self, *args, **opts):
        from billing.services.ps_group_service import (
            suggest_groups_by_exact_name,
            suggest_groups_by_head_token,
        )

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
                if opts["dry_run"]:
                    # Wrap-and-rollback: lets us see what the run would
                    # do without persisting. Inner @atomic in the
                    # service is a savepoint within this outer one.
                    with db_transaction.atomic():
                        if not opts["skip_exact"]:
                            ec = suggest_groups_by_exact_name(company)
                            self.stdout.write(f"  Exact-name (dry): {ec}")
                        if not opts["skip_head"]:
                            hc = suggest_groups_by_head_token(
                                company, head_size=opts["head_size"]
                            )
                            self.stdout.write(f"  Head-token (dry): {hc}")
                        db_transaction.set_rollback(True)
                else:
                    if not opts["skip_exact"]:
                        ec = suggest_groups_by_exact_name(company)
                        self.stdout.write(f"  Exact-name: {ec}")
                    if not opts["skip_head"]:
                        hc = suggest_groups_by_head_token(
                            company, head_size=opts["head_size"]
                        )
                        self.stdout.write(f"  Head-token: {hc}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  FAILED for {company.subdomain}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS("\nDone."))
