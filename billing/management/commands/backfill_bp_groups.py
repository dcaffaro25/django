# -*- coding: utf-8 -*-
"""
Backfill BusinessPartnerGroup state for one or all tenants.

Two passes per tenant:
  1. Materialize matriz/filial Groups for every BP whose cnpj_root has
     2+ siblings (mirrors what BusinessPartner.save now does on every
     persist; this catches existing data).
  2. Replay accepted NF↔Tx links into Group suggestions for cross-root
     consolidation cases that the matcher couldn't infer alone.

Both passes are idempotent — re-runs do not duplicate state.

Examples:
    python manage.py backfill_bp_groups --tenant evolat --dry-run
    python manage.py backfill_bp_groups --tenant evolat
    python manage.py backfill_bp_groups --all-tenants
    python manage.py backfill_bp_groups --tenant evolat --skip-roots
    python manage.py backfill_bp_groups --tenant evolat --skip-links
"""
from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Materialize matriz/filial Groups + replay accepted NF↔Tx links "
        "into cross-root Group suggestions."
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
        parser.add_argument(
            "--skip-roots", action="store_true",
            help="Skip the cnpj_root materialization pass.",
        )
        parser.add_argument(
            "--skip-links", action="store_true",
            help="Skip the NF↔Tx link replay pass.",
        )

    def handle(self, *args, **opts):
        from billing.models import BusinessPartner, NFTransactionLink
        from billing.services.bp_group_service import (
            ensure_root_group, resolve_bp_by_cnpj, upsert_membership_suggestion,
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

            # ----- Pass 1: cnpj_root materialization -----
            if not opts["skip_roots"]:
                self.stdout.write("  [1/2] Materializing cnpj_root clusters…")
                bps = (
                    BusinessPartner.objects
                    .filter(company=company)
                    .exclude(cnpj_root="")
                    .exclude(cnpj_root__isnull=True)
                    .order_by("id")
                )
                touched = 0
                created_groups = 0
                root_errors = 0
                seen_groups: set = set()
                for bp in bps.iterator(chunk_size=500):
                    if opts["dry_run"]:
                        # No write; just count BPs that would be processed.
                        touched += 1
                        continue
                    try:
                        g = ensure_root_group(bp)
                        touched += 1
                        if g is not None and g.id not in seen_groups:
                            seen_groups.add(g.id)
                            created_groups += 1
                    except Exception as e:
                        root_errors += 1
                        self.stderr.write(
                            f"  ! bp id={bp.id}: {type(e).__name__}: {e}"
                        )
                self.stdout.write(
                    f"    bps_visited={touched} "
                    f"groups_touched={created_groups} "
                    f"errors={root_errors} "
                    f"{'(dry-run)' if opts['dry_run'] else ''}"
                )

            # ----- Pass 2: NF↔Tx link replay -----
            if not opts["skip_links"]:
                self.stdout.write("  [2/2] Replaying accepted NF↔Tx links…")
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
                    f"    inspected={inspected} "
                    f"suggested={suggested} "
                    f"same_bp={same_bp} "
                    f"unresolved={unresolved} "
                    f"errors={errors} "
                    f"{'(dry-run)' if opts['dry_run'] else ''}"
                )
