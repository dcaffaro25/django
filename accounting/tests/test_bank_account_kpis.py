"""Tests for the Bank Account dashboard / detail KPI services that
power the new BankAccountsPage + BankAccountDetailPage.

Three callable surfaces under test:
  * compute_dashboard_kpis  -- org-wide aggregates + per-currency sums
  * compute_account_kpis    -- per-account detail header
  * compute_monthly_flows   -- 12-month inflow/outflow series

Reconciliation rate is count-basis in v1 (matched bank txs / total
bank txs in window). Inflow/outflow are signed amounts. "Stale"
means older than N days AND not in any matched/approved rec.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

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
from accounting.services.bank_account_kpis import (
    compute_account_kpis,
    compute_dashboard_kpis,
    compute_monthly_flows,
)
from multitenancy.models import Company, Entity


# Fixed clock so date-relative metrics (stale, MTD, window) are
# deterministic. Without this the test results would shift every day.
FIXED_TODAY = dt.date(2026, 5, 15)


def _patch_today():
    """Decorator-friendly mock: patches the service's _today() helper
    so all date arithmetic anchors to FIXED_TODAY."""
    return mock.patch(
        "accounting.services.bank_account_kpis._today",
        return_value=FIXED_TODAY,
    )


class _BankAccountKpisFixtureMixin:
    """Shared fixture builder. Uses a fixed clock so every test sees
    the same "today" regardless of when CI runs."""

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="KpiCo", subdomain="kpico")
        cls.entity = Entity.objects.create(company=cls.company, name="Acme")
        cls.brl = Currency.objects.create(code="BRL", name="Real")
        cls.usd = Currency.objects.create(code="USD", name="Dollar")
        cls.account = Account.objects.create(
            company=cls.company, account_code="3.0", name="Caixa",
            account_direction=1, balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1), currency=cls.brl,
        )
        cls.bank = Bank.objects.create(
            name="KPI Bank", country="Brasil", bank_code="KPI001",
        )
        # Two BRL accounts + one USD account so currency-grouping is
        # exercised in dashboard tests.
        cls.ba_brl_a = BankAccount.objects.create(
            company=cls.company, entity=cls.entity, bank=cls.bank,
            currency=cls.brl, name="BRL-A", account_number="A-1",
            account_type="checking",
            balance=Decimal("1000.00"), balance_date=dt.date(2026, 1, 1),
        )
        cls.ba_brl_b = BankAccount.objects.create(
            company=cls.company, entity=cls.entity, bank=cls.bank,
            currency=cls.brl, name="BRL-B", account_number="B-1",
            account_type="checking",
            balance=Decimal("500.00"), balance_date=dt.date(2026, 1, 1),
        )
        cls.ba_usd = BankAccount.objects.create(
            company=cls.company, entity=cls.entity, bank=cls.bank,
            currency=cls.usd, name="USD-A", account_number="U-1",
            account_type="checking",
            balance=Decimal("200.00"), balance_date=dt.date(2026, 1, 1),
        )

    def _bank_tx(
        self,
        bank_account: BankAccount,
        amount: str,
        date: dt.date,
        description: str = "test",
    ) -> BankTransaction:
        return BankTransaction.objects.create(
            company=self.company,
            bank_account=bank_account,
            currency=bank_account.currency,
            date=date,
            amount=Decimal(amount),
            description=description,
        )

    def _journal_entry(self, debit: str) -> JournalEntry:
        tx = Transaction.objects.create(
            company=self.company, entity=self.entity, currency=self.brl,
            date=dt.date(2026, 4, 27), amount=Decimal(debit),
            description="parent",
        )
        return JournalEntry.objects.create(
            company=self.company, transaction=tx, account=self.account,
            date=dt.date(2026, 4, 27), debit_amount=Decimal(debit),
        )

    def _match(
        self,
        status: str,
        bank_txs: list[BankTransaction],
        jes: list[JournalEntry],
    ):
        rec = Reconciliation.objects.create(company=self.company, status=status)
        rec.bank_transactions.set(bank_txs)
        rec.journal_entries.set(jes)
        return rec


class ComputeDashboardKpisTests(_BankAccountKpisFixtureMixin, TestCase):
    """Aggregations across multiple accounts + currencies."""

    def setUp(self):
        # Fresh-per-test bank txs so account_count etc. don't drift.
        BankTransaction.objects.filter(company=self.company).delete()
        Reconciliation.objects.filter(company=self.company).delete()

    def test_empty_returns_zero_aggregates(self):
        with _patch_today():
            kpis = compute_dashboard_kpis(
                bank_account_qs=BankAccount.objects.filter(company=self.company),
            )
        self.assertEqual(kpis["account_count"], 3)
        self.assertEqual(kpis["stale_unreconciled_count"], 0)
        self.assertEqual(kpis["reconciliation_rate_pct"], 0)
        self.assertEqual(kpis["inflow_mtd_by_currency"], {})
        self.assertEqual(kpis["outflow_mtd_by_currency"], {})

    def test_per_currency_inflow_outflow_aggregates_correctly(self):
        # MTD = May 2026; FIXED_TODAY = 2026-05-15.
        self._bank_tx(self.ba_brl_a, "1000.00", dt.date(2026, 5, 5))   # inflow BRL
        self._bank_tx(self.ba_brl_b, "-300.00", dt.date(2026, 5, 10))  # outflow BRL
        self._bank_tx(self.ba_usd, "50.00", dt.date(2026, 5, 8))       # inflow USD
        # April -- outside MTD, inside the 30-day window.
        self._bank_tx(self.ba_brl_a, "200.00", dt.date(2026, 4, 28))
        with _patch_today():
            kpis = compute_dashboard_kpis(
                bank_account_qs=BankAccount.objects.filter(company=self.company),
                recon_window_days=30,
            )
        self.assertEqual(kpis["inflow_mtd_by_currency"], {"BRL": "1000.00", "USD": "50.00"})
        self.assertEqual(kpis["outflow_mtd_by_currency"], {"BRL": "300.00"})
        # Window (last 30 days from 2026-05-15 = 2026-04-15..) picks up
        # the 2026-04-28 inflow too.
        self.assertEqual(kpis["inflow_window_by_currency"]["BRL"], "1200.00")

    def test_stale_count_excludes_matched_recs(self):
        # FIXED_TODAY = 2026-05-15; stale_days=30 -> cutoff 2026-04-15.
        old = self._bank_tx(self.ba_brl_a, "100.00", dt.date(2026, 3, 1))   # stale
        old_matched = self._bank_tx(self.ba_brl_a, "200.00", dt.date(2026, 3, 5))
        old_open = self._bank_tx(self.ba_brl_a, "300.00", dt.date(2026, 3, 10))
        je = self._journal_entry(debit="200.00")
        self._match("matched", [old_matched], [je])
        self._match("open", [old_open], [je])

        with _patch_today():
            kpis = compute_dashboard_kpis(
                bank_account_qs=BankAccount.objects.filter(company=self.company),
                stale_days=30,
            )
        # ``old`` + ``old_open`` count as stale (open != matched/approved);
        # ``old_matched`` is excluded.
        self.assertEqual(kpis["stale_unreconciled_count"], 2)

    def test_recon_rate_count_basis(self):
        """Window: 30 days back from 2026-05-15 = 2026-04-15.
        Two recent bank txs, one matched -> 50%."""
        bt1 = self._bank_tx(self.ba_brl_a, "100.00", dt.date(2026, 5, 1))
        bt2 = self._bank_tx(self.ba_brl_a, "200.00", dt.date(2026, 5, 2))
        je = self._journal_entry(debit="100.00")
        self._match("matched", [bt1], [je])
        # bt2 unmatched.
        with _patch_today():
            kpis = compute_dashboard_kpis(
                bank_account_qs=BankAccount.objects.filter(company=self.company),
                recon_window_days=30,
            )
        self.assertEqual(kpis["reconciliation_rate_pct"], 50)


class ComputeAccountKpisTests(_BankAccountKpisFixtureMixin, TestCase):
    """Per-account header strip values."""

    def setUp(self):
        BankTransaction.objects.filter(company=self.company).delete()
        Reconciliation.objects.filter(company=self.company).delete()

    def test_empty_account_returns_safe_defaults(self):
        with _patch_today():
            kpis = compute_account_kpis(bank_account=self.ba_brl_a)
        self.assertEqual(kpis["transaction_count"], 0)
        self.assertEqual(kpis["stale_unreconciled_count"], 0)
        self.assertEqual(kpis["reconciliation_rate_pct"], 0)
        self.assertEqual(kpis["inflow_mtd"], "0")
        self.assertEqual(kpis["outflow_mtd"], "0")
        self.assertIsNone(kpis["last_transaction_at"])
        self.assertIsNone(kpis["last_reconciliation_at"])

    def test_inflow_outflow_signed_amounts(self):
        self._bank_tx(self.ba_brl_a, "500.00", dt.date(2026, 5, 5))   # inflow MTD
        self._bank_tx(self.ba_brl_a, "-200.00", dt.date(2026, 5, 7))  # outflow MTD
        self._bank_tx(self.ba_brl_a, "100.00", dt.date(2026, 4, 30))  # inflow window
        with _patch_today():
            kpis = compute_account_kpis(bank_account=self.ba_brl_a)
        self.assertEqual(kpis["inflow_mtd"], "500.00")
        self.assertEqual(kpis["outflow_mtd"], "200.00")
        self.assertEqual(kpis["inflow_window"], "600.00")

    def test_only_counts_account_specific_txs(self):
        """A KPI for ba_brl_a must NOT include txs on ba_brl_b."""
        self._bank_tx(self.ba_brl_a, "100.00", dt.date(2026, 5, 1))
        self._bank_tx(self.ba_brl_b, "999.00", dt.date(2026, 5, 1))  # noise
        with _patch_today():
            kpis = compute_account_kpis(bank_account=self.ba_brl_a)
        self.assertEqual(kpis["transaction_count"], 1)
        self.assertEqual(kpis["inflow_mtd"], "100.00")


class ComputeMonthlyFlowsTests(_BankAccountKpisFixtureMixin, TestCase):
    """Inflow/outflow series for the per-account bar chart."""

    def setUp(self):
        BankTransaction.objects.filter(company=self.company).delete()
        Reconciliation.objects.filter(company=self.company).delete()

    def test_emits_zero_filled_continuous_months(self):
        # FIXED_TODAY = 2026-05-15. Asking for 3 months should give
        # March / April / May 2026 in order regardless of activity.
        with _patch_today():
            flows = compute_monthly_flows(
                bank_account=self.ba_brl_a, months=3,
            )
        self.assertEqual(len(flows), 3)
        self.assertEqual(flows[0]["month"], "2026-03")
        self.assertEqual(flows[1]["month"], "2026-04")
        self.assertEqual(flows[2]["month"], "2026-05")
        # All zero.
        for f in flows:
            self.assertEqual(f["inflow"], "0")
            self.assertEqual(f["outflow"], "0")

    def test_aggregates_by_month(self):
        self._bank_tx(self.ba_brl_a, "100.00", dt.date(2026, 3, 5))
        self._bank_tx(self.ba_brl_a, "200.00", dt.date(2026, 3, 15))
        self._bank_tx(self.ba_brl_a, "-50.00", dt.date(2026, 3, 20))
        self._bank_tx(self.ba_brl_a, "75.00", dt.date(2026, 5, 1))
        with _patch_today():
            flows = compute_monthly_flows(
                bank_account=self.ba_brl_a, months=3,
            )
        self.assertEqual(flows[0]["month"], "2026-03")
        self.assertEqual(flows[0]["inflow"], "300.00")
        self.assertEqual(flows[0]["outflow"], "50.00")
        self.assertEqual(flows[1]["month"], "2026-04")
        self.assertEqual(flows[1]["inflow"], "0")
        self.assertEqual(flows[1]["outflow"], "0")
        self.assertEqual(flows[2]["month"], "2026-05")
        self.assertEqual(flows[2]["inflow"], "75.00")

    def test_signs_normalised_to_abs_outflow(self):
        """Outflows are negative on the source row but emitted as
        absolute values (the bar chart displays magnitudes)."""
        self._bank_tx(self.ba_brl_a, "-500.00", dt.date(2026, 5, 1))
        with _patch_today():
            flows = compute_monthly_flows(
                bank_account=self.ba_brl_a, months=1,
            )
        self.assertEqual(flows[0]["outflow"], "500.00")
        self.assertEqual(flows[0]["inflow"], "0")
