# -*- coding: utf-8 -*-
"""
Promote every balanced + pending Transaction to ``state='posted'``.

The per-Tx posting workflow (``transaction_service.post_transaction``)
is wired but never auto-triggered. Tenants accumulate balanced-but-
unposted rows indefinitely. This command is the bulk fix; running it
once brings the tenant current. The matching API endpoint
``/api/transactions/bulk-post-balanced/`` does the same from the UI.

Examples:
    python manage.py post_balanced_transactions --tenant evolat --dry-run
    python manage.py post_balanced_transactions --tenant evolat
    python manage.py post_balanced_transactions --all-tenants
"""
from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Bulk-post every Tx with state='pending' AND is_balanced=True. "
        "Mirrors ``bring_invoice_status_current`` for the GL side."
    )

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--tenant", help="Subdomain of the tenant.")
        scope.add_argument(
            "--all-tenants", action="store_true",
            help="Run for every tenant.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would change; do not write.",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Optional cap (0 = no cap).",
        )

    def handle(self, *args, **opts):
        from accounting.services.transaction_service import (
            bulk_post_balanced_transactions,
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
                res = bulk_post_balanced_transactions(
                    company,
                    dry_run=opts["dry_run"],
                    limit=opts["limit"],
                )
                self.stdout.write(
                    f"  scanned (pending + balanced): {res['scanned_pending_balanced']}"
                )
                if opts["dry_run"]:
                    self.stdout.write(f"  would_post: {res['would_post']}")
                else:
                    self.stdout.write(f"  posted    : {res['posted']}")
                    self.stdout.write(f"  failed    : {res['failed']}")
                if res["samples"]:
                    self.stdout.write(f"  samples:")
                    for s in res["samples"]:
                        self.stdout.write(
                            f"    Tx#{s['id']} date={s['date']} amount={s['amount']}"
                        )
                if res["failures"]:
                    self.stdout.write(self.style.WARNING(f"  failures:"))
                    for f in res["failures"]:
                        self.stdout.write(f"    Tx#{f['id']}: {f['error']}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  FAILED for {company.subdomain}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS("\nDone."))
