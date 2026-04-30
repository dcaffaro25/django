# -*- coding: utf-8 -*-
"""
Targeted Invoice backfill — Option C from the planning discussion.

Creates Invoices ONLY for NFs that have at least one accepted (or, with
``--include-suggested``, suggested) NFTransactionLink. The Tx-link is the
strong signal that the NF represents real money flowing through the GL,
which avoids the 6,529-Invoice mass-creation that turning the global
``auto_create_invoice_from_nf`` flag on would trigger.

Skips:
- NFs that already have an Invoice attached (idempotent).
- NFs where the counterparty CNPJ matches the tenant CNPJ root
  (self-billing — handled by nf_invoice_sync._is_self_cnpj).

Bypasses ``BillingTenantConfig.auto_create_invoice_from_nf`` and the
finalidade/tipo whitelist via ``force=True`` — the upstream Tx-link
filter is the gate. Operators can still narrow the cohort with
``--finalidade`` / ``--tipo``.

Examples:
    python manage.py backfill_invoices_from_tx_linked_nfs --tenant evolat --dry-run
    python manage.py backfill_invoices_from_tx_linked_nfs --tenant evolat
    python manage.py backfill_invoices_from_tx_linked_nfs --tenant evolat --include-suggested
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction

from multitenancy.models import Company


class Command(BaseCommand):
    help = (
        "Create Invoices for NFs that have a Tx-link (accepted-only by default). "
        "Idempotent: NFs already attached to an Invoice are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant subdomain (e.g. evolat).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Compute counters without writing.")
        parser.add_argument(
            "--include-suggested", action="store_true",
            help="Also include NFs whose only Tx-link is in 'suggested' state. "
                 "Default: only 'accepted' links count as a real-money signal.",
        )
        parser.add_argument(
            "--finalidade", type=int, action="append",
            help="Restrict to NFs with this finalidade (1=Normal, 2=Compl, 3=Ajuste, 4=Devol). "
                 "Repeatable; default: 1 (Normal only).",
        )
        parser.add_argument(
            "--tipo", type=int, action="append",
            help="Restrict to NFs with this tipo_operacao (0=Entrada, 1=Saida). "
                 "Repeatable; default: 1 (Saida only).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Process at most this many NFs (after filtering).",
        )

    def handle(self, *args, **opts):
        from billing.models import NotaFiscal, NFTransactionLink
        from billing.services.nf_invoice_sync import match_or_create_invoice_for_nf

        try:
            company = Company.objects.get(subdomain=opts["tenant"])
        except Company.DoesNotExist as e:
            raise CommandError(f"Tenant '{opts['tenant']}' not found.") from e

        accepted_states = [NFTransactionLink.REVIEW_ACCEPTED]
        if opts["include_suggested"]:
            accepted_states.append(NFTransactionLink.REVIEW_SUGGESTED)

        finalidades = opts["finalidade"] or [1]
        tipos = opts["tipo"] or [1]

        qs = (
            NotaFiscal.objects
            .filter(
                company=company,
                transaction_links__review_status__in=accepted_states,
                tipo_operacao__in=tipos,
                finalidade__in=finalidades,
                invoice_attachments__isnull=True,
            )
            .distinct()
            .order_by("-data_emissao")
        )
        total = qs.count()
        if opts["limit"]:
            qs = qs[: opts["limit"]]
            self.stdout.write(f"Cohort: {total} NFs (limited to {opts['limit']}).")
        else:
            self.stdout.write(f"Cohort: {total} NFs.")

        counters = Counter()
        created_ids = []
        for nf in qs.iterator(chunk_size=200):
            try:
                with db_transaction.atomic():
                    res = match_or_create_invoice_for_nf(
                        nf, dry_run=opts["dry_run"], force=True,
                    )
            except Exception as e:
                counters["errors"] += 1
                self.stderr.write(self.style.ERROR(
                    f"  NF#{nf.id} (numero={nf.numero}): {e}"
                ))
                continue

            if res.get("matched_invoice_id"):
                counters["matched"] += 1
            elif res.get("created_invoice_id") not in (None,):
                counters["created"] += 1
                if not opts["dry_run"] and res["created_invoice_id"] != -1:
                    created_ids.append(res["created_invoice_id"])
            elif res.get("skipped_reason"):
                counters[f"skipped:{res['skipped_reason']}"] += 1

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Tenant {company.subdomain} (id={company.id}) ===",
        ))
        self.stdout.write(f"  Mode: {'DRY-RUN' if opts['dry_run'] else 'COMMIT'}")
        for key in sorted(counters):
            self.stdout.write(f"  {key}: {counters[key]}")
        if created_ids:
            sample = created_ids[:5]
            self.stdout.write(
                f"  Created Invoice IDs (first {len(sample)}): {sample}"
            )
        self.stdout.write(self.style.SUCCESS("\nDone."))
