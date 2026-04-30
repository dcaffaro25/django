# -*- coding: utf-8 -*-
"""
Sweep all Invoices for a tenant and report coherence critics.

The same ``audit_critics_for_company`` service powers the
``POST /api/invoices/audit-critics/`` endpoint, so the CLI and UI surfaces
stay in sync.

Examples:
    python manage.py audit_invoice_critics --tenant evolat
    python manage.py audit_invoice_critics --tenant evolat --severity error,warning
    python manage.py audit_invoice_critics --tenant evolat --no-persist
    python manage.py audit_invoice_critics --tenant evolat --csv out.csv
"""
import csv

from django.core.management.base import BaseCommand, CommandError

from multitenancy.models import Company


class Command(BaseCommand):
    help = "Audit Invoice coherence critics across a tenant; prints a summary."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant subdomain (e.g. evolat).")
        parser.add_argument(
            "--severity",
            help="Comma-separated severities to include in per-invoice items "
                 "(e.g. error,warning). Aggregate counts always cover all.",
        )
        parser.add_argument(
            "--include-acknowledged",
            action="store_true",
            help="By default acknowledged critics are excluded from counts. "
                 "Use this flag to include them.",
        )
        parser.add_argument(
            "--no-persist",
            action="store_true",
            help="Skip writing critics_count back to Invoice rows.",
        )
        parser.add_argument(
            "--csv",
            help="Write the per-invoice critic list to this CSV file.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Only show the first N invoices in the printed summary.",
        )

    def handle(self, *args, **opts):
        from billing.services.critics_service import audit_critics_for_company

        try:
            company = Company.objects.get(subdomain=opts["tenant"])
        except Company.DoesNotExist as e:
            raise CommandError(f"Tenant '{opts['tenant']}' not found.") from e

        sev_filter = None
        if opts["severity"]:
            sev_filter = tuple(s.strip() for s in opts["severity"].split(",") if s.strip())

        result = audit_critics_for_company(
            company,
            only_unacknowledged=not opts["include_acknowledged"],
            severity_in=sev_filter,
            persist=not opts["no_persist"],
        )

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Tenant {company.subdomain} (id={company.id}) ===",
        ))
        self.stdout.write(f"  Swept: {result['swept']}")
        self.stdout.write(f"  Invoices with critics: {result['invoices_with_critics_count']}")
        self.stdout.write(f"  By severity: {result['by_severity']}")
        self.stdout.write(f"  By kind: {result['by_kind']}")

        rows = result["results"]
        if opts["limit"]:
            rows = rows[: opts["limit"]]

        if rows:
            self.stdout.write("\n  Invoices ranked by error count then total:")
            for r in rows:
                sev = r["by_severity"]
                self.stdout.write(
                    f"    Invoice #{r['invoice_id']:6} {r['invoice_number']:>15}  "
                    f"err={sev.get('error', 0)} warn={sev.get('warning', 0)} "
                    f"info={sev.get('info', 0)}"
                )

        if opts["csv"]:
            with open(opts["csv"], "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow([
                    "invoice_id", "invoice_number", "partner_id",
                    "total_amount", "fiscal_status",
                    "kind", "severity", "subject_type", "subject_id",
                    "message", "acknowledged",
                ])
                for r in result["results"]:
                    for it in r["items"]:
                        w.writerow([
                            r["invoice_id"], r["invoice_number"], r["partner_id"],
                            r["total_amount"], r["fiscal_status"],
                            it["kind"], it["severity"], it["subject_type"],
                            it["subject_id"], it["message"], it["acknowledged"],
                        ])
            self.stdout.write(self.style.SUCCESS(f"\nCSV written: {opts['csv']}"))

        self.stdout.write(self.style.SUCCESS("\nDone."))
