# -*- coding: utf-8 -*-
"""
Promote ``Invoice.status`` to ``paid`` for invoices whose linked
NF↔Tx evidence shows the cash already moved (and was matched +
reconciled).

This is a one-shot fix for tenants whose invoice-status pipeline
fell behind. The auto-update hook on ``accept_link`` /
reconciliation finalize keeps things current going forward; this
command catches the existing backlog.

Examples:
    python manage.py bring_invoice_status_current --tenant evolat --dry-run
    python manage.py bring_invoice_status_current --tenant evolat
    python manage.py bring_invoice_status_current --all-tenants
"""
from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Walk Invoice -> NF -> Tx and mark invoices as ``paid`` when "
        "every linked Tx is reconciled. One-shot backfill; the hook "
        "on accept_link + reconciliation finalize keeps it current."
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
            "--include-non-open", action="store_true",
            help=(
                "Re-evaluate ALL sale invoices, not just ``issued`` / "
                "``partially_paid``. Use after a model migration or "
                "to verify nothing is wrong with already-paid rows."
            ),
        )

    def handle(self, *args, **opts):
        from billing.services.invoice_payment_evidence import (
            backfill_invoice_status_from_recon,
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
                res = backfill_invoice_status_from_recon(
                    company,
                    only_open=not opts["include_non_open"],
                    dry_run=opts["dry_run"],
                )
                self.stdout.write(f"  scanned        : {res['scanned']}")
                self.stdout.write(
                    f"  would_promote  : {res['would_promote']}  "
                    f"(R$ {res['promoted_amount']})"
                )
                if not opts["dry_run"]:
                    self.stdout.write(f"  promoted       : {res['promoted']}")
                self.stdout.write(f"  by_evidence:")
                for k, v in res["by_evidence"].items():
                    self.stdout.write(f"    {k:28s} {v}")
                if res["samples"]:
                    self.stdout.write(f"  samples:")
                    for s in res["samples"]:
                        self.stdout.write(
                            f"    Inv#{s['invoice_id']} num={s['invoice_number']} "
                            f"amt={s['amount']} old={s['old_status']} "
                            f"tx={s['tx_ids']}"
                        )
            except Exception as e:
                self.stderr.write(self.style.ERROR(
                    f"  FAILED for {company.subdomain}: {e}"
                ))

        self.stdout.write(self.style.SUCCESS("\nDone."))
