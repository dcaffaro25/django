"""Tests for the per-bank-transaction match metrics surfaced in
``BankTransactionSerializer`` via ``_bank_tx_match_metrics``.

The metrics power the Workbench / list page chip that tells operators
how much of a bank tx is reconciled vs remaining when it's part of an
``open`` reconciliation. The math is M:M-aware: when a single rec
links multiple bank txs to multiple journal entries, we apportion the
matched JE value to each bank tx by its share of the rec's total
bank amount.

These tests pin every branch:
  * fully unmatched bank tx (no recs) -> 0 / amt / 0%
  * fully matched (status=matched, recon balanced) -> amt / 0 / 100%
  * partially matched (status=open, half the JEs) -> 0.5 / 0.5 / 50%
  * inactive rec status (pending/unmatched) ignored
  * over-match clamped at 100% / 0 remaining
  * zero-amount bank tx returns zeros (no division by zero)
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounting.models import (
    Account,
    Bank,
    BankAccount,
    BankTransaction,
    Currency,
    JournalEntry,
    Reconciliation,
    Transaction,
)
from accounting.serializers import (
    BankTransactionSerializer,
    _bank_tx_match_metrics,
)
from multitenancy.models import Company, Entity


User = get_user_model()


class BankTxMatchMetricsTests(TestCase):
    """Pure-function coverage for ``_bank_tx_match_metrics``. No HTTP
    layer; we exercise the math directly with model rows."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="MetricsCo", subdomain="metricsco")
        cls.entity = Entity.objects.create(company=cls.company, name="Acme Counterparty")
        cls.currency = Currency.objects.create(code="BRL", name="Real")
        # Account is needed for JournalEntry FK.
        cls.account = Account.objects.create(
            company=cls.company,
            account_code="1.0",
            name="Caixa",
            # +1 = asset (debit-positive), the direction the JE math
            # in ``Account.balance`` multiplies by. Required field.
            account_direction=1,
            balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
            currency=cls.currency,
        )
        cls.bank = Bank.objects.create(
            name="Itaú",
            country="Brasil",
            bank_code="ITAU341",
        )
        cls.bank_account = BankAccount.objects.create(
            company=cls.company,
            entity=cls.entity,
            bank=cls.bank,
            currency=cls.currency,
            name="Itaú CC 123-4",
            account_number="123-4",
            account_type="checking",
            balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
        )

    # --- helpers --------------------------------------------------------

    def _bank_tx(self, amount: str, **kwargs):
        return BankTransaction.objects.create(
            company=self.company,
            bank_account=self.bank_account,
            currency=self.currency,
            date=dt.date(2026, 4, 27),
            amount=Decimal(amount),
            description=kwargs.get("description", "test tx"),
            **{k: v for k, v in kwargs.items() if k not in ("description",)},
        )

    def _journal_entry(self, debit: str | None = None, credit: str | None = None):
        # ``JournalEntry.get_amount()`` returns ``debit_amount`` when
        # not None, else ``credit_amount``. Important: passing 0 (not
        # None) for the un-used side makes get_amount return 0 and the
        # apportionment math collapses. So leave the un-used side as
        # None here.
        debit_d = Decimal(debit) if debit is not None else None
        credit_d = Decimal(credit) if credit is not None else None
        # Need a parent Transaction for the JE FK.
        tx = Transaction.objects.create(
            company=self.company,
            entity=self.entity,
            currency=self.currency,
            date=dt.date(2026, 4, 27),
            amount=debit_d if debit_d is not None else (credit_d or Decimal("0")),
            description="test parent",
        )
        return JournalEntry.objects.create(
            company=self.company,
            transaction=tx,
            account=self.account,
            date=dt.date(2026, 4, 27),
            debit_amount=debit_d,
            credit_amount=credit_d,
        )

    def _reconciliation(self, status: str, bank_txs: list, journal_entries: list):
        rec = Reconciliation.objects.create(company=self.company, status=status)
        rec.bank_transactions.set(bank_txs)
        rec.journal_entries.set(journal_entries)
        return rec

    # --- tests ----------------------------------------------------------

    def test_no_reconciliations_means_fully_unmatched(self):
        bt = self._bank_tx("1000.00")
        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("0.00"))
        self.assertEqual(remaining, Decimal("1000.00"))
        self.assertEqual(pct, 0)

    def test_fully_matched_reconciliation_returns_100_pct(self):
        bt = self._bank_tx("1000.00")
        je = self._journal_entry(debit="1000.00")
        self._reconciliation("matched", [bt], [je])
        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("1000.00"))
        self.assertEqual(remaining, Decimal("0.00"))
        self.assertEqual(pct, 100)

    def test_open_partial_reconciliation_apportions_to_bank_tx_share(self):
        """A bank tx of 1000 in an ``open`` rec with one JE of 600
        should report 60% reconciled / 400 remaining."""
        bt = self._bank_tx("1000.00")
        je = self._journal_entry(debit="600.00")
        self._reconciliation("open", [bt], [je])
        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("600.00"))
        self.assertEqual(remaining, Decimal("400.00"))
        self.assertEqual(pct, 60)

    def test_open_rec_with_two_bank_txs_apportions_by_share(self):
        """Two bank txs (300 + 700) in one open rec with a JE of 500.
        Apportionment: bt1 gets share=0.3 of JE total -> matched=150;
        bt2 gets share=0.7 -> matched=350."""
        bt1 = self._bank_tx("300.00", description="a")
        bt2 = self._bank_tx("700.00", description="b")
        je = self._journal_entry(debit="500.00")
        self._reconciliation("open", [bt1, bt2], [je])

        matched1, remaining1, pct1 = _bank_tx_match_metrics(bt1)
        matched2, remaining2, pct2 = _bank_tx_match_metrics(bt2)
        self.assertEqual(matched1, Decimal("150.00"))
        self.assertEqual(remaining1, Decimal("150.00"))
        self.assertEqual(pct1, 50)
        self.assertEqual(matched2, Decimal("350.00"))
        self.assertEqual(remaining2, Decimal("350.00"))
        self.assertEqual(pct2, 50)

    def test_inactive_rec_status_is_ignored(self):
        """A reconciliation in ``unmatched`` (rejected) or ``pending``
        (no JEs yet) should NOT contribute to matched. Only
        matched/approved/open count."""
        bt = self._bank_tx("1000.00")
        je = self._journal_entry(debit="1000.00")
        self._reconciliation("unmatched", [bt], [je])

        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("0.00"))
        self.assertEqual(remaining, Decimal("1000.00"))
        self.assertEqual(pct, 0)

    def test_over_match_clamps_to_100_pct(self):
        """Operator linked extra JEs (rare but legal). Remaining
        clamps at 0 instead of going negative."""
        bt = self._bank_tx("1000.00")
        je_big = self._journal_entry(debit="1500.00")
        self._reconciliation("matched", [bt], [je_big])

        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("1000.00"))
        self.assertEqual(remaining, Decimal("0.00"))
        self.assertEqual(pct, 100)

    def test_zero_amount_bank_tx_returns_zeros(self):
        """Avoid division by zero on a zero-amount bank tx (rare but
        legal: e.g. a fee reversal that nets to 0)."""
        bt = self._bank_tx("0.00")
        je = self._journal_entry(debit="100.00")
        self._reconciliation("matched", [bt], [je])

        matched, remaining, pct = _bank_tx_match_metrics(bt)
        self.assertEqual(matched, Decimal("0.00"))
        self.assertEqual(remaining, Decimal("0.00"))
        self.assertEqual(pct, 0)

    def test_serializer_emits_three_fields(self):
        """End-to-end: BankTransactionSerializer renders the three
        new fields with the correct values for an open partial."""
        bt = self._bank_tx("1000.00")
        je = self._journal_entry(debit="250.00")
        self._reconciliation("open", [bt], [je])

        data = BankTransactionSerializer(bt).data
        self.assertEqual(data["amount_reconciled"], "250.00")
        self.assertEqual(data["amount_remaining"], "750.00")
        self.assertEqual(data["match_progress_pct"], 25)


class BankTxReconciliationHistoryEndpointTests(TestCase):
    """Coverage for the new audit endpoint
    ``GET /<tenant>/api/bank_transactions/<id>/reconciliation-history/``
    that powers the Workbench's per-bank-tx history drawer.

    These tests use the HTTP layer (APIClient) so they exercise the
    full URL routing, ScopedQuerysetMixin, prefetch, serialization,
    and ordering pipeline -- not just the inner method.
    """

    @classmethod
    def setUpTestData(cls):
        from rest_framework.authtoken.models import Token
        cls.company = Company.objects.create(name="HistoryCo", subdomain="historyco")
        cls.entity = Entity.objects.create(company=cls.company, name="Acme")
        cls.currency = Currency.objects.create(code="USD", name="Dollar")
        cls.account = Account.objects.create(
            company=cls.company, account_code="2.0", name="Receita",
            account_direction=1, balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1), currency=cls.currency,
        )
        cls.bank = Bank.objects.create(
            name="HistoryBank", country="BR", bank_code="HIST001",
        )
        cls.bank_account = BankAccount.objects.create(
            company=cls.company, entity=cls.entity, bank=cls.bank,
            currency=cls.currency, name="HistAccount", account_number="555-1",
            account_type="checking", balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
        )
        cls.user = User.objects.create_user(username="histuser", password="x")

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _bank_tx(self, amount: str):
        return BankTransaction.objects.create(
            company=self.company, bank_account=self.bank_account,
            currency=self.currency, date=dt.date(2026, 4, 27),
            amount=Decimal(amount), description="hist tx",
        )

    def _journal_entry(self, debit: str):
        tx = Transaction.objects.create(
            company=self.company, entity=self.entity, currency=self.currency,
            date=dt.date(2026, 4, 27), amount=Decimal(debit), description="hist parent",
        )
        return JournalEntry.objects.create(
            company=self.company, transaction=tx, account=self.account,
            date=dt.date(2026, 4, 27), debit_amount=Decimal(debit),
        )

    def _url(self, bank_tx_id: int) -> str:
        return f"/{self.company.id}/api/bank_transactions/{bank_tx_id}/reconciliation-history/"

    def test_no_history_returns_empty_array(self):
        bt = self._bank_tx("100.00")
        resp = self.client.get(self._url(bt.id))
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json(), [])

    def test_returns_one_entry_per_reconciliation(self):
        bt = self._bank_tx("1000.00")
        je1 = self._journal_entry(debit="600.00")
        je2 = self._journal_entry(debit="400.00")
        rec1 = Reconciliation.objects.create(
            company=self.company, status="open", reference="first attempt",
        )
        rec1.bank_transactions.set([bt])
        rec1.journal_entries.set([je1])

        rec2 = Reconciliation.objects.create(
            company=self.company, status="matched", reference="closed",
        )
        rec2.bank_transactions.set([bt])
        rec2.journal_entries.set([je2])

        resp = self.client.get(self._url(bt.id))
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(len(body), 2)
        # Most-recent first ordering: rec2 was created last, expect index 0.
        self.assertEqual(body[0]["id"], rec2.id)
        self.assertEqual(body[0]["status"], "matched")
        self.assertEqual(body[0]["reference"], "closed")
        self.assertEqual(body[0]["total_bank_amount"], "1000.00")
        self.assertEqual(body[0]["total_journal_amount"], "400.00")
        self.assertEqual(body[0]["discrepancy"], "600.00")
        self.assertEqual(body[0]["bank_transaction_count"], 1)
        self.assertEqual(body[0]["journal_entry_count"], 1)
        self.assertEqual(body[1]["id"], rec1.id)
        self.assertEqual(body[1]["status"], "open")

    def test_404_on_unknown_bank_tx(self):
        resp = self.client.get(self._url(999_999))
        self.assertEqual(resp.status_code, 404)
