"""Backfill the missing cash leg on Transactions created by the old
(pre-PR-8) reconciliation flow.

Context: prior to PR 8, ``BankTransactionViewSet.create_suggestions``
wrote a single contra JE per suggestion and called it a day, leaving
the Transaction unbalanced (Σdebit ≠ Σcredit). The new flow creates
both legs. This command scans for the legacy rows and posts the
missing cash leg so the ledger becomes balanced retroactively.

Usage::

    python manage.py reconcile_missing_cash_legs --dry-run
    python manage.py reconcile_missing_cash_legs --apply
    python manage.py reconcile_missing_cash_legs --apply --company-id 3
    python manage.py reconcile_missing_cash_legs --apply --limit 100

The ``--dry-run`` form reports what would be written without touching
the DB. Run it first, inspect the tallies, then rerun with
``--apply``. The command is idempotent — re-applying is a no-op
because the scan only picks up transactions whose Σdebit ≠ Σcredit.

Accuracy notes:

* We resolve the bank account for each target Transaction via the
  Reconciliation it belongs to. A Transaction with no Reconciliation
  (orphan) is skipped — we can't reliably pick its cash account.
* If a transaction belongs to multiple reconciliations spanning
  different bank accounts, we skip it and report it under
  ``ambiguous``.
* If the bank account has no active CoA ``Account`` linked, the
  Transaction is skipped and reported under ``unmapped_bank``.
* The fix posts a SINGLE balancing leg on the resolved cash account,
  with debit/credit set to close the gap in one hit. Amounts come
  straight from the existing imbalance — no guessing.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.db.models import DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models import (
    Account,
    JournalEntry,
    Reconciliation,
    Transaction,
)


class Command(BaseCommand):
    help = "Post the missing cash leg on pre-PR-8 unbalanced Transactions."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--apply", action="store_true", help="Actually write. Without this, it's a dry run.")
        parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default behavior).")
        parser.add_argument("--company-id", type=int, default=None, help="Limit to a single company.")
        parser.add_argument("--limit", type=int, default=None, help="Cap the number of Transactions processed.")

    def handle(self, *args, **opts) -> None:
        apply_changes = bool(opts["apply"]) and not bool(opts["dry_run"])
        company_id: int | None = opts["company_id"]
        limit: int | None = opts["limit"]

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.NOTICE(f"=== reconcile_missing_cash_legs [{mode}] ==="))

        # ------------------------------------------------------------------
        # 1) Find unbalanced Transactions.
        #    A Transaction is unbalanced when Σdebit ≠ Σcredit across its
        #    JournalEntries. ``Coalesce`` guards against null aggregates
        #    on transactions with no JEs (rare but possible).
        # ------------------------------------------------------------------
        unbalanced_qs = (
            Transaction.objects
            .annotate(
                _d=Coalesce(Sum("journal_entries__debit_amount"),
                            Value(Decimal("0"), output_field=DecimalField(max_digits=18, decimal_places=2))),
                _c=Coalesce(Sum("journal_entries__credit_amount"),
                            Value(Decimal("0"), output_field=DecimalField(max_digits=18, decimal_places=2))),
            )
            .filter(~Q(_d=F("_c")))
        )
        if company_id is not None:
            unbalanced_qs = unbalanced_qs.filter(company_id=company_id)
        if limit is not None:
            unbalanced_qs = unbalanced_qs[: max(1, limit)]

        unbalanced: list[Transaction] = list(unbalanced_qs.select_related("company"))
        total = len(unbalanced)
        self.stdout.write(f"Found {total} unbalanced Transaction(s).")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        # ------------------------------------------------------------------
        # 2) For each tx, resolve the bank account via its Reconciliation
        #    membership. Group into "fixable" / "ambiguous" / "orphan" /
        #    "unmapped_bank".
        # ------------------------------------------------------------------
        stats: dict[str, int] = defaultdict(int)
        fixable: list[tuple[Transaction, Decimal, Account]] = []
        # Pre-load transaction -> reconciliations -> bank_accounts via Prefetch would
        # also work; a simple loop is plenty fast at backfill volumes.
        for tx in unbalanced:
            d = tx._d or Decimal("0")
            c = tx._c or Decimal("0")
            imbalance = d - c  # positive -> too many debits; negative -> too many credits
            if imbalance == 0:
                continue  # raced with a concurrent fix; skip

            recs = list(
                Reconciliation.objects
                .filter(journal_entries__transaction_id=tx.id)
                .distinct()
                .prefetch_related("bank_transactions")
            )
            bank_account_ids: set[int] = set()
            for r in recs:
                for bt in r.bank_transactions.all():
                    if bt.bank_account_id:
                        bank_account_ids.add(bt.bank_account_id)

            if not bank_account_ids:
                stats["orphan"] += 1
                self._line(f"  · TX#{tx.id} imbalance={imbalance} -> no reconciliation with bank tx; skipped")
                continue
            if len(bank_account_ids) > 1:
                stats["ambiguous"] += 1
                self._line(f"  · TX#{tx.id} imbalance={imbalance} -> multiple bank accounts {sorted(bank_account_ids)}; skipped")
                continue

            (bank_account_id,) = bank_account_ids
            cash_account = (
                Account.objects
                .filter(company_id=tx.company_id, bank_account_id=bank_account_id, is_active=True)
                .first()
            )
            if cash_account is None:
                stats["unmapped_bank"] += 1
                self._line(f"  · TX#{tx.id} -> bank_account {bank_account_id} has no active CoA; skipped")
                continue

            stats["fixable"] += 1
            fixable.append((tx, imbalance, cash_account))

        self.stdout.write(
            self.style.NOTICE(
                f"Classification: fixable={stats['fixable']} "
                f"orphan={stats['orphan']} ambiguous={stats['ambiguous']} "
                f"unmapped_bank={stats['unmapped_bank']}"
            )
        )

        # ------------------------------------------------------------------
        # 3) Post the balancing leg, or report what would be posted.
        # ------------------------------------------------------------------
        now = timezone.now()
        posted = 0
        for tx, imbalance, cash_account in fixable:
            # To rebalance: if debits > credits by X, we need a CREDIT of X
            # on the cash account. Conversely, extra credits -> DEBIT of |X|.
            #
            # This mirrors the direction-independent raw-balance rule used
            # by :func:`accounting.services.bank_ledger.assert_transaction_balanced`.
            if imbalance > 0:
                debit_amount = None
                credit_amount = imbalance
            else:
                debit_amount = -imbalance
                credit_amount = None

            desc = f"Cash leg backfill (PR 8) for recon of bank_account {cash_account.bank_account_id}"
            if apply_changes:
                with db_transaction.atomic():
                    JournalEntry.objects.create(
                        company_id=tx.company_id,
                        transaction=tx,
                        account=cash_account,
                        debit_amount=debit_amount,
                        credit_amount=credit_amount,
                        description=desc,
                        date=tx.date,
                        state=tx.state,
                        notes=f"reconcile_missing_cash_legs @ {now.isoformat()}",
                    )
                posted += 1
                if posted % 25 == 0:
                    self.stdout.write(f"  · posted {posted}/{stats['fixable']}...")
            else:
                self._line(
                    f"  · TX#{tx.id} company={tx.company_id} "
                    f"cash_acct={cash_account.account_code or cash_account.id} "
                    f"-> would post D={debit_amount or 0} C={credit_amount or 0}"
                )

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(f"Posted {posted} cash legs."))
        else:
            self.stdout.write(self.style.WARNING(
                f"Dry-run complete. Re-run with --apply to write {stats['fixable']} legs."
            ))

    # -------- tiny helper so the loop reads cleanly even when verbose

    def _line(self, msg: str) -> None:
        self.stdout.write(msg)
