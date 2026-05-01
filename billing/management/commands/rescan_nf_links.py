# -*- coding: utf-8 -*-
"""
Backfill / rescan NF↔Tx links for one or all tenants.

Examples:
    python manage.py rescan_nf_links --tenant evolat --dry-run
    python manage.py rescan_nf_links --tenant evolat --auto-accept-above 0.95
    python manage.py rescan_nf_links --all-tenants --min-confidence 0.5
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = "Re-run NF↔Transaction matching and persist suggestions to NFTransactionLink."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument(
            "--tenant",
            help="Subdomain of the tenant to scan.",
        )
        scope.add_argument(
            "--all-tenants",
            action="store_true",
            help="Run for every tenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute matches but do not write to NFTransactionLink.",
        )
        parser.add_argument(
            "--min-confidence",
            type=str,
            default="0.5",
            help="Drop matches below this score.",
        )
        parser.add_argument(
            "--auto-accept-above",
            type=str,
            default="1.001",
            help="Auto-accept matches at or above this score (default 1.001 = never).",
        )
        parser.add_argument(
            "--date-window-days",
            type=int,
            default=7,
            help="Tolerance in days for date matching.",
        )
        parser.add_argument(
            "--amount-tolerance",
            type=str,
            default="0.01",
            help="Proportional amount tolerance (0.01 = 1%%).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum candidates per tenant (after dedup + sort).",
        )
        parser.add_argument(
            "--audit-existing",
            action="store_true",
            help=(
                "After the scan, re-score every existing 'suggested' "
                "link against the current logic. Auto-rejects rows whose "
                "Tx sign disagrees with the NF (chargebacks) or whose "
                "score has fallen below --min-confidence. Boosts rows "
                "whose score increased (e.g. parcela detection). "
                "Useful after rolling out scoring changes to clean up "
                "the queue without re-scanning fresh candidates."
            ),
        )

    def handle(self, *args, **opts):
        from billing.services.nf_link_service import (
            audit_suggested_links, find_candidates, persist_links,
        )

        if opts["all_tenants"]:
            companies = Company.objects.all()
        else:
            try:
                companies = [Company.objects.get(subdomain=opts["tenant"])]
            except Company.DoesNotExist as e:
                raise CommandError(f"Tenant '{opts['tenant']}' not found.") from e

        try:
            min_conf = Decimal(opts["min_confidence"])
            auto_accept = Decimal(opts["auto_accept_above"])
            tol = Decimal(opts["amount_tolerance"])
        except Exception as e:
            raise CommandError(f"Invalid decimal arg: {e}")

        for company in companies:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n=== Tenant {company.subdomain} (id={company.id}) ===",
            ))
            try:
                matches = find_candidates(
                    company,
                    date_window_days=opts["date_window_days"],
                    amount_tolerance=tol,
                    min_confidence=min_conf,
                    limit=opts["limit"],
                )
                self.stdout.write(f"  Candidates: {len(matches)}")
                counters = persist_links(
                    company, matches,
                    auto_accept_above=auto_accept,
                    dry_run=opts["dry_run"],
                )
                self.stdout.write(f"  Persisted: {counters}")
                if opts["audit_existing"]:
                    audit = audit_suggested_links(
                        company,
                        date_window_days=opts["date_window_days"],
                        amount_tolerance=tol,
                        min_confidence=min_conf,
                        dry_run=opts["dry_run"],
                    )
                    self.stdout.write(f"  Audit: {audit}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  FAILED for {company.subdomain}: {e}"))

        self.stdout.write(self.style.SUCCESS("\nDone."))
