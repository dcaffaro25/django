# -*- coding: utf-8 -*-
"""
Backfill BusinessPartnerGroup suggestions from already-accepted NFTransactionLinks.

Each accepted NF↔Tx link where the Tx's CNPJ resolves to a different BP
than the NF's counterparty becomes a Group suggestion. Re-runs are
idempotent — same source link doesn't double-count.

Examples:
    python manage.py backfill_bp_groups --tenant evolat --dry-run
    python manage.py backfill_bp_groups --tenant evolat
    python manage.py backfill_bp_groups --all-tenants
"""
from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Replay accepted NF↔Tx links to populate BusinessPartnerGroup "
        "suggestions retroactively."
    )

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--tenant", help="Subdomain of the tenant to backfill.")
        scope.add_argument(
            "--all-tenants", action="store_true",
            help="Run for every tenant.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Walk the data but don't write anything.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Maximum number of accepted links to inspect per tenant.",
        )

    def handle(self, *args, **opts):
        from billing.models import NFTransactionLink
        from billing.services.bp_group_service import (
            resolve_bp_by_cnpj, upsert_membership_suggestion,
        )
        from billing.services.nf_invoice_sync import _resolve_partner_for_nf

        if opts["all_tenants"]:
            companies = Company.objects.all()
        else:
            try:
                companies = [Company.objects.get(subdomain=opts["tenant"])]
            except Company.DoesNotExist as e:
                raise CommandError(f"Tenant '{opts['tenant']}' not found.") from e

        for company in companies:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n=== Tenant {company.subdomain} (id={company.id}) ===",
            ))
            qs = (
                NFTransactionLink.objects
                .filter(
                    company=company,
                    review_status=NFTransactionLink.REVIEW_ACCEPTED,
                )
                .select_related("transaction", "nota_fiscal")
                .order_by("id")
            )
            if opts["limit"]:
                qs = qs[: opts["limit"]]

            inspected = 0
            same_bp = 0
            unresolved = 0
            suggested = 0
            errors = 0

            for link in qs.iterator(chunk_size=500):
                inspected += 1
                tx = link.transaction
                nf = link.nota_fiscal
                if not tx or not nf:
                    unresolved += 1
                    continue
                bp_tx = resolve_bp_by_cnpj(tx.company, getattr(tx, "cnpj", None))
                bp_nf = _resolve_partner_for_nf(nf)
                if bp_tx is None or bp_nf is None:
                    unresolved += 1
                    continue
                if bp_tx.id == bp_nf.id:
                    same_bp += 1
                    continue
                if opts["dry_run"]:
                    suggested += 1
                    continue
                try:
                    upsert_membership_suggestion(
                        bp_tx, bp_nf,
                        method="nf_tx_link",
                        source_id=link.id,
                        confidence=link.confidence,
                    )
                    suggested += 1
                except Exception as e:
                    errors += 1
                    self.stderr.write(
                        f"  ! link id={link.id}: {type(e).__name__}: {e}"
                    )

            self.stdout.write(
                f"  inspected={inspected} "
                f"suggested={suggested} "
                f"same_bp={same_bp} "
                f"unresolved={unresolved} "
                f"errors={errors} "
                f"{'(dry-run)' if opts['dry_run'] else ''}"
            )
