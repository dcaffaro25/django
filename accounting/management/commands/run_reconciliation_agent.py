# -*- coding: utf-8 -*-
"""
Run the autonomous reconciliation agent for one or all tenants.

Examples:
    python manage.py run_reconciliation_agent --tenant evolat --dry-run
    python manage.py run_reconciliation_agent --tenant evolat --auto-accept 0.95 --limit 50
    python manage.py run_reconciliation_agent --all-tenants --min-confidence 0.6

The agent only auto-accepts the safest cohort (existing balanced JE +
high confidence + dominant over second-best). Everything else is logged
as ``ambiguous``/``no_match``/``not_applicable`` for human review. See
``accounting/services/reconciliation_agent_service.py`` for the full
decision logic.
"""
from datetime import date as _date_cls
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from accounting.services.reconciliation_agent_service import ReconciliationAgent
from multitenancy.models import Company


class Command(BaseCommand):
    help = "Run the reconciliation agent over unreconciled bank transactions."

    def add_arguments(self, parser):
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument(
            "--tenant",
            help="Subdomain of the tenant to process.",
        )
        scope.add_argument(
            "--all-tenants",
            action="store_true",
            help="Run for every tenant.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compute decisions and persist run/decision rows but do NOT create reconciliations.",
        )
        parser.add_argument(
            "--auto-accept",
            type=str,
            default=None,
            help="Auto-accept threshold (default: settings.RECONCILIATION_AGENT_AUTO_ACCEPT_THRESHOLD or 0.95).",
        )
        parser.add_argument(
            "--ambiguity-gap",
            type=str,
            default=None,
            help="Min gap between top and second suggestion (default: 0.10).",
        )
        parser.add_argument(
            "--min-confidence",
            type=str,
            default=None,
            help="Below this, mark as no_match (default: 0.50).",
        )
        parser.add_argument(
            "--bank-account-id",
            type=int,
            default=None,
            help="Restrict to a single bank account.",
        )
        parser.add_argument(
            "--date-from",
            type=str,
            default=None,
            help="Inclusive lower bound (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--date-to",
            type=str,
            default=None,
            help="Inclusive upper bound (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap on bank transactions inspected per tenant.",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if opts["all_tenants"]:
            companies = list(Company.objects.order_by("id"))
        else:
            try:
                companies = [Company.objects.get(subdomain=opts["tenant"])]
            except Company.DoesNotExist:
                raise CommandError(f"Tenant {opts['tenant']!r} not found.")

        date_from = _parse_date(opts.get("date_from"))
        date_to = _parse_date(opts.get("date_to"))

        for company in companies:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"\n=== {company.subdomain} (id={company.id}) ===",
                )
            )
            try:
                agent = ReconciliationAgent(
                    company_id=company.id,
                    auto_accept_threshold=opts.get("auto_accept"),
                    ambiguity_gap=opts.get("ambiguity_gap"),
                    min_confidence=opts.get("min_confidence"),
                    dry_run=opts["dry_run"],
                    triggered_by="management_command",
                )
                result = agent.run(
                    bank_account_id=opts.get("bank_account_id"),
                    date_from=date_from,
                    date_to=date_to,
                    limit=opts.get("limit"),
                )
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  FAILED for {company.subdomain}: {exc}")
                )
                continue

            self.stdout.write(
                f"  run_id={result.run_id} "
                f"candidates={result.n_candidates} "
                f"auto_accepted={result.n_auto_accepted} "
                f"ambiguous={result.n_ambiguous} "
                f"no_match={result.n_no_match} "
                f"not_applicable={result.n_not_applicable} "
                f"errors={result.n_errors}"
            )
            if opts["dry_run"]:
                self.stdout.write(
                    self.style.WARNING(
                        "  --dry-run: decisions persisted, but no Reconciliations created."
                    )
                )


def _parse_date(value):
    if not value:
        return None
    try:
        return _date_cls.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Invalid date {value!r}: {exc}")
