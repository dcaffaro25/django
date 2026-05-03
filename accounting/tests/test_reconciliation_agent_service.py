"""Tests for ``accounting.services.reconciliation_agent_service``.

The agent's I/O surface is two classes (``ReconciliationAgent``,
``AgentRunResult``) and an audit-table pair (``ReconciliationAgentRun``,
``ReconciliationAgentDecision``). We pin the **decision logic** here by
mocking out :class:`BankTransactionSuggestionService` — the embedding
service is heavy and not under test.

Each test exercises one branch of ``_process_one``:

* no suggestions          → ``no_match``
* below min_confidence    → ``no_match``
* min ≤ x < auto_accept   → ``ambiguous``
* above + tight gap       → ``ambiguous``
* above + dominant, but
  ``create_new``          → ``not_applicable``
* above + dominant, but
  unbalanced              → ``not_applicable``
* above + dominant + safe → ``auto_accepted`` (real Reconciliation)
* dry-run + safe          → ``auto_accepted`` decision, NO Reconciliation
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounting.models import (
    Account,
    Bank,
    BankAccount,
    BankTransaction,
    Currency,
    JournalEntry,
    Reconciliation,
    ReconciliationAgentDecision,
    ReconciliationAgentRun,
    Transaction,
)
from accounting.services.reconciliation_agent_service import (
    OUTCOME_AMBIGUOUS,
    OUTCOME_AUTO_ACCEPTED,
    OUTCOME_NO_MATCH,
    OUTCOME_NOT_APPLICABLE,
    ReconciliationAgent,
)
from multitenancy.models import Company, Entity


class ReconciliationAgentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(name="AgentCo", subdomain="agentco")
        cls.entity = Entity.objects.create(company=cls.company, name="Counterparty")
        cls.currency = Currency.objects.create(code="BRL", name="Real")
        cls.account = Account.objects.create(
            company=cls.company,
            account_code="1.0",
            name="Caixa",
            account_direction=1,
            balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
            currency=cls.currency,
        )
        cls.bank = Bank.objects.create(name="Itaú", country="Brasil", bank_code="ITAU341")
        cls.bank_account = BankAccount.objects.create(
            company=cls.company,
            entity=cls.entity,
            bank=cls.bank,
            currency=cls.currency,
            name="Itaú CC",
            account_number="111",
            account_type="checking",
            balance=Decimal("0.00"),
            balance_date=dt.date(2026, 1, 1),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _bank_tx(self, amount="100.00"):
        return BankTransaction.objects.create(
            company=self.company,
            bank_account=self.bank_account,
            currency=self.currency,
            date=dt.date(2026, 4, 27),
            amount=Decimal(amount),
            description="agent test tx",
        )

    def _journal_entry(self, debit="100.00"):
        tx = Transaction.objects.create(
            company=self.company,
            entity=self.entity,
            currency=self.currency,
            date=dt.date(2026, 4, 27),
            amount=Decimal(debit),
            description="agent parent tx",
        )
        return JournalEntry.objects.create(
            company=self.company,
            transaction=tx,
            account=self.account,
            date=dt.date(2026, 4, 27),
            debit_amount=Decimal(debit),
        )

    def _wrap(self, bank_tx_id, suggestions):
        """Build the wrapper payload that BankTransactionSuggestionService
        returns from ``suggest_book_transactions``."""
        return {
            "suggestions": [
                {"bank_transaction_id": bank_tx_id, "suggestions": suggestions},
            ],
            "errors": [],
        }

    def _safe_use_existing(self, je_id, *, confidence="0.97", balanced=True):
        """Build a ``use_existing_book`` suggestion that's structurally safe
        for auto-accept (balanced, no complementing JEs, has existing JE)."""
        return {
            "suggestion_type": "use_existing_book",
            "confidence_score": float(confidence),
            "similarity": 0.95,
            "amount_match_score": 1.0,
            "is_balanced": balanced,
            "complementing_journal_entries": [],
            "existing_journal_entry": {"id": je_id, "account_id": self.account.id},
            "bank_transaction_id": None,
        }

    def _agent(self, **overrides):
        defaults = dict(
            company_id=self.company.id,
            auto_accept_threshold="0.95",
            ambiguity_gap="0.10",
            min_confidence="0.50",
            dry_run=False,
            triggered_by="test",
        )
        defaults.update(overrides)
        return ReconciliationAgent(**defaults)

    # ------------------------------------------------------------------
    # no_match: no suggestions returned
    # ------------------------------------------------------------------
    def test_no_suggestions_marks_no_match(self):
        bt = self._bank_tx()
        agent = self._agent()
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, []),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_candidates, 1)
        self.assertEqual(result.n_no_match, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        decision = ReconciliationAgentDecision.objects.get(run_id=result.run_id)
        self.assertEqual(decision.outcome, OUTCOME_NO_MATCH)

    # ------------------------------------------------------------------
    # no_match: below min_confidence
    # ------------------------------------------------------------------
    def test_below_min_confidence_marks_no_match(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent()
        sug = self._safe_use_existing(je.id, confidence="0.40")
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_no_match, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        self.assertFalse(Reconciliation.objects.exists())

    # ------------------------------------------------------------------
    # ambiguous: top above min, below auto_accept
    # ------------------------------------------------------------------
    def test_mid_confidence_marks_ambiguous(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent()
        sug = self._safe_use_existing(je.id, confidence="0.80")
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_ambiguous, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        self.assertFalse(Reconciliation.objects.exists())

    # ------------------------------------------------------------------
    # ambiguous: top above auto_accept but second is too close
    # ------------------------------------------------------------------
    def test_top_above_but_second_too_close_marks_ambiguous(self):
        bt = self._bank_tx()
        je1 = self._journal_entry()
        je2 = self._journal_entry()
        agent = self._agent(ambiguity_gap="0.10")
        top = self._safe_use_existing(je1.id, confidence="0.97")
        second = self._safe_use_existing(je2.id, confidence="0.94")  # gap = 0.03 < 0.10
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [top, second]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_ambiguous, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        self.assertFalse(Reconciliation.objects.exists())

    # ------------------------------------------------------------------
    # not_applicable: top is create_new (not safe for auto)
    # ------------------------------------------------------------------
    def test_create_new_suggestion_marks_not_applicable(self):
        bt = self._bank_tx()
        agent = self._agent()
        sug = {
            "suggestion_type": "create_new",
            "confidence_score": 0.99,
            "is_balanced": True,
            "complementing_journal_entries": [],
        }
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_not_applicable, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        self.assertFalse(Reconciliation.objects.exists())

    # ------------------------------------------------------------------
    # not_applicable: use_existing_book but unbalanced
    # ------------------------------------------------------------------
    def test_unbalanced_use_existing_marks_not_applicable(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent()
        sug = self._safe_use_existing(je.id, confidence="0.99", balanced=False)
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_not_applicable, 1)
        self.assertFalse(Reconciliation.objects.exists())

    # ------------------------------------------------------------------
    # auto_accepted: full safe path creates real Reconciliation
    # ------------------------------------------------------------------
    def test_safe_high_confidence_auto_accepts(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent()
        sug = self._safe_use_existing(je.id, confidence="0.97")
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_auto_accepted, 1)
        self.assertEqual(Reconciliation.objects.count(), 1)

        recon = Reconciliation.objects.first()
        self.assertEqual(recon.status, "matched")
        self.assertIn(bt, recon.bank_transactions.all())
        self.assertIn(je, recon.journal_entries.all())

        bt.refresh_from_db()
        je.refresh_from_db()
        self.assertTrue(bt.balance_validated)
        self.assertTrue(je.is_reconciled)

        decision = ReconciliationAgentDecision.objects.get(run_id=result.run_id)
        self.assertEqual(decision.outcome, OUTCOME_AUTO_ACCEPTED)
        self.assertEqual(decision.reconciliation_id, recon.id)

    # ------------------------------------------------------------------
    # dry-run: decision rows persist, NO Reconciliation
    # ------------------------------------------------------------------
    def test_dry_run_records_decisions_without_creating_reconciliation(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent(dry_run=True)
        sug = self._safe_use_existing(je.id, confidence="0.97")
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_auto_accepted, 1)
        self.assertFalse(Reconciliation.objects.exists())  # nothing created
        bt.refresh_from_db()
        je.refresh_from_db()
        self.assertFalse(bt.balance_validated)
        self.assertFalse(je.is_reconciled)

        run = ReconciliationAgentRun.objects.get(id=result.run_id)
        self.assertTrue(run.dry_run)
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.n_auto_accepted, 1)

    # ------------------------------------------------------------------
    # auto_accepted with no second: no gap check applies
    # ------------------------------------------------------------------
    def test_safe_high_confidence_with_no_second_auto_accepts(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        agent = self._agent()
        sug = self._safe_use_existing(je.id, confidence="0.99")
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value=self._wrap(bt.id, [sug]),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_auto_accepted, 1)
        self.assertEqual(Reconciliation.objects.count(), 1)

    # ------------------------------------------------------------------
    # error handling: suggestion service raises
    # ------------------------------------------------------------------
    def test_suggestion_service_error_records_error_decision(self):
        bt = self._bank_tx()
        agent = self._agent()
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            side_effect=RuntimeError("embedding svc down"),
        ):
            result = agent.run(limit=5)

        self.assertEqual(result.n_errors, 1)
        self.assertEqual(result.n_auto_accepted, 0)
        decision = ReconciliationAgentDecision.objects.get(run_id=result.run_id)
        self.assertEqual(decision.outcome, "error")
        self.assertIn("embedding svc down", decision.error_message)

    # ------------------------------------------------------------------
    # candidate filter: already-reconciled bank txs are excluded
    # ------------------------------------------------------------------
    def test_already_reconciled_bank_txs_are_excluded(self):
        bt = self._bank_tx()
        je = self._journal_entry()
        # Pre-existing matched recon — should keep the bank tx out of the cohort
        rec = Reconciliation.objects.create(company=self.company, status="matched")
        rec.bank_transactions.set([bt])
        rec.journal_entries.set([je])

        agent = self._agent()
        with patch.object(
            agent._suggestion_service,
            "suggest_book_transactions",
            return_value={"suggestions": [], "errors": []},
        ) as m:
            result = agent.run(limit=5)

        self.assertEqual(result.n_candidates, 0)
        m.assert_not_called()
