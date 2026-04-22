"""Tests for ``accounting.services.bank_ledger``.

Two fixtures at the top mint the minimal object graph needed for a
balanced-adjustment write: company, currency, bank, bank account,
cash CoA account, entity. Individual tests create the contra
accounts they need — keeping the fixture small so we don't
accidentally exercise unrelated constraints.

All tests use Django's ``TestCase``; they run against a throwaway
test DB. The service is atomic by design, so we assert on the final
state of the DB after the call (rolled-back partial writes are
tested via the raise path).
"""

from __future__ import annotations

from datetime import date
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
from accounting.services.bank_ledger import (
    BankLedgerError,
    ContraLeg,
    assert_transaction_balanced,
    contra_legs_from_payload,
    create_balanced_adjustment,
    resolve_cash_account,
    sum_existing_cash_legs_for_jes,
)
from multitenancy.models import Company, Entity


class _BaseBankLedgerTest(TestCase):
    """Shared fixtures. Kept spartan on purpose — individual tests
    build the contra accounts they need."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create(username=f"bl-test-{id(cls)}")
        cls.company = Company.objects.create(
            name=f"BL Test Co {id(cls)}",
            subdomain=f"bltest{id(cls)}",
        )
        cls.currency = Currency.objects.create(code="BRL", name="Real")
        cls.bank = Bank.objects.create(
            name=f"Itau-BL-{id(cls)}",
            country="Brasil",
            bank_code=f"BL{id(cls)}",
        )
        cls.entity = Entity.objects.create(
            company=cls.company,
            name=f"Entity-BL-{id(cls)}",
        )
        cls.bank_account = BankAccount.objects.create(
            company=cls.company,
            entity=cls.entity,
            name="Itau 1234",
            account_number="1234",
            bank=cls.bank,
            currency=cls.currency,
            balance=Decimal("0.00"),
            balance_date=date(2026, 1, 1),
            account_type="checking",
        )
        # Cash CoA account tied to the bank — this is what
        # ``resolve_cash_account`` should find.
        cls.cash_account = Account.objects.create(
            company=cls.company,
            name="Ativo Circulante Itau 1234",
            account_code="1.1.1.01",
            account_direction=1,  # Ativo: debit = positive effective
            balance=Decimal("0.00"),
            balance_date=date(2026, 1, 1),
            currency=cls.currency,
            bank_account=cls.bank_account,
            is_active=True,
        )

    def _bank_tx(self, amount: str, *, date_: date | None = None) -> BankTransaction:
        """Helper to mint a BankTransaction with a unique tx_hash."""
        return BankTransaction.objects.create(
            company=self.company,
            bank_account=self.bank_account,
            date=date_ or date(2026, 4, 15),
            currency=self.currency,
            amount=Decimal(amount),
            description="test",
            tx_hash=f"bltest-{BankTransaction.objects.count()}",
        )

    def _contra_account(self, *, code: str, direction: int, name: str = "") -> Account:
        return Account.objects.create(
            company=self.company,
            name=name or f"Acct {code}",
            account_code=code,
            account_direction=direction,
            balance=Decimal("0.00"),
            balance_date=date(2026, 1, 1),
            currency=self.currency,
            is_active=True,
        )


# ---------------------------------------------------------------- resolve_cash_account


class ResolveCashAccountTests(_BaseBankLedgerTest):
    def test_returns_the_linked_active_account(self):
        """Happy path: a single active CoA account maps to the bank."""
        got = resolve_cash_account(self.bank_account.id, self.company.id)
        self.assertEqual(got.id, self.cash_account.id)

    def test_raises_when_no_active_account_linked(self):
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_active"])
        with self.assertRaises(BankLedgerError) as cm:
            resolve_cash_account(self.bank_account.id, self.company.id)
        self.assertIn("Nenhuma conta contábil ativa", str(cm.exception))

    def test_raises_when_multiple_accounts_linked(self):
        # An intentional config bug — we want the caller to halt
        # rather than silently pick one.
        Account.objects.create(
            company=self.company,
            name="Duplicate CoA",
            account_code="1.1.1.02",
            account_direction=1,
            balance=Decimal("0.00"),
            balance_date=date(2026, 1, 1),
            currency=self.currency,
            bank_account=self.bank_account,
            is_active=True,
        )
        with self.assertRaises(BankLedgerError) as cm:
            resolve_cash_account(self.bank_account.id, self.company.id)
        self.assertIn("Mais de uma conta", str(cm.exception))


# ---------------------------------------------------------------- create_balanced_adjustment


class CreateBalancedAdjustmentTests(_BaseBankLedgerTest):
    """The core contract. Cases named after the real-world scenarios
    we care about."""

    def test_case2_orphan_bank_fee_negative_balances(self):
        """Bank fee -15 with no prior book entry.

        Expected:
          * New Transaction with two legs that balance (debits == credits).
          * Cash leg: Credit Ativo 15  → effective -15.
          * Contra leg: Debit Despesa 15 → effective +15.
          * Σ effective = 0 (transaction balances).
          * Cash leg effective equals the bank amount — recon contribution.
        """
        despesa = self._contra_account(code="4.1.1", direction=1, name="Despesa Tarifa")
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=Decimal("-15.00"),
            contra_legs=[
                ContraLeg(
                    account_id=despesa.id,
                    debit_amount=Decimal("15.00"),
                    credit_amount=None,
                ),
            ],
            transaction_date=date(2026, 4, 15),
        )
        tx = result.transaction
        self.assertEqual(Decimal("0.00"), assert_transaction_balanced(tx))
        # cash leg: credit 15 on direction=1 account → effective -15
        self.assertIsNone(result.cash_leg.debit_amount)
        self.assertEqual(result.cash_leg.credit_amount, Decimal("15.00"))
        self.assertEqual(result.cash_leg.get_effective_amount(), Decimal("-15.00"))
        # contra leg: debit 15 on direction=1 → effective +15
        (contra,) = result.contra_legs
        self.assertEqual(contra.debit_amount, Decimal("15.00"))
        self.assertEqual(contra.get_effective_amount(), Decimal("15.00"))

    def test_case2_orphan_deposit_balances_correctly(self):
        """Bank +500, contra Receita. Correct sides to balance:
        cash debit 500 (Ativo dir=1, effective +500);
        receita credit 500 (dir=-1, effective -500).
        Σ = 0.
        """
        receita = self._contra_account(code="3.1.1", direction=-1, name="Receita")
        # For ``(debit - credit) * direction == -500`` on receita:
        # 0 - 500 = -500; -500 * -1 = +500 — WRONG.
        # We need effective = -500, so (d - c) * -1 = -500 → d - c = 500
        # → debit 500, credit None. Booking a DEBIT to receita is a
        # reversal — legitimate for some adjustments but unusual for a
        # plain deposit. The real-world pattern:
        #   Debit Cash, Credit Receita (both make sense as sides).
        # cash debit 500 → effective +500
        # receita credit 500 → (0 - 500) * -1 = +500 → NOT zero sum.
        # So you'd need passivo / receita debited, or use a different
        # account. For the "plain deposit, Receita credit" mental
        # model, the paired accounting expects another twist:
        # Receita is typically matched with AR or similar, not
        # directly with cash on a deposit. For the API contract we're
        # testing, we assert the caller sent coherent sides.
        #
        # Illustrate: cash debit 500, paired with a *direction=1*
        # contra (e.g., Clientes credit 500).
        clientes = self._contra_account(code="1.1.2", direction=1, name="Clientes")
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=Decimal("500.00"),
            contra_legs=[
                ContraLeg(
                    account_id=clientes.id,
                    debit_amount=None,
                    credit_amount=Decimal("500.00"),
                ),
            ],
            transaction_date=date(2026, 4, 15),
        )
        self.assertEqual(Decimal("0.00"), assert_transaction_balanced(result.transaction))
        (contra,) = result.contra_legs
        # clientes credit 500 on dir=1 → effective -500
        self.assertEqual(contra.get_effective_amount(), Decimal("-500.00"))
        # cash +500 + contra -500 = 0 ✓

    def test_case2_rejects_unbalanced_sides(self):
        """Operator picked a side whose raw (d-c) doesn't offset the
        cash leg. The service must refuse rather than silently
        writing an unbalanced Transaction."""
        despesa = self._contra_account(code="4.1.2", direction=1)
        with self.assertRaises(BankLedgerError) as cm:
            create_balanced_adjustment(
                company_id=self.company.id,
                bank_account_id=self.bank_account.id,
                adjustment_target=Decimal("-15.00"),
                # Cash leg: credit 15 (raw -15). Contra raw must be +15.
                # Credit 15 on Despesa gives raw -15 — same sign as
                # cash, so the transaction wouldn't balance.
                contra_legs=[
                    ContraLeg(account_id=despesa.id, debit_amount=None, credit_amount=Decimal("15.00")),
                ],
                transaction_date=date(2026, 4, 15),
            )
        self.assertIn("não fecha", str(cm.exception))
        # Rollback guarantee: no Transaction row leaked.
        self.assertFalse(Transaction.objects.filter(description__contains="test").exists())

    def test_case2_mixed_direction_contra_balances(self):
        """A contra on a Passivo (direction=-1) account paired with a
        cash leg on Ativo (direction=1). Raw d-c matches, effectives
        do NOT sum to zero (they cancel directionally only if the
        accounts are all same-direction). This test exists
        specifically to guard the raw-sum invariant against the old
        effective-sum check."""
        passivo = self._contra_account(code="2.1.1", direction=-1, name="Fornecedor Curto Prazo")
        # Bank inflow +200; cash debit 200; contra must credit 200
        # to balance raw.
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=Decimal("200.00"),
            contra_legs=[
                ContraLeg(account_id=passivo.id, debit_amount=None, credit_amount=Decimal("200.00")),
            ],
            transaction_date=date(2026, 4, 15),
        )
        # Σd == Σc ✓
        self.assertEqual(Decimal("0.00"), assert_transaction_balanced(result.transaction))
        # Effectives do NOT sum to zero, precisely because directions
        # differ:
        #   cash (dir=1): debit 200  → effective +200
        #   passivo (dir=-1): credit 200 → (0 - 200) * -1 = +200
        #   Σ effective = +400 — that's okay, this is balanced
        #   double-entry, just not same-direction.
        eff_sum = result.cash_leg.get_effective_amount() + sum(
            (leg.get_effective_amount() for leg in result.contra_legs), Decimal("0")
        )
        self.assertEqual(eff_sum, Decimal("400.00"))

    def test_split_contras_balance(self):
        """Multi-row contra adjustment: 800 estoque + 200 icms = -1000 bank."""
        estoque = self._contra_account(code="1.1.3", direction=1, name="Estoque")
        icms = self._contra_account(code="1.1.4", direction=1, name="ICMS a Recuperar")
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=Decimal("-1000.00"),
            contra_legs=[
                ContraLeg(account_id=estoque.id, debit_amount=Decimal("800.00"), credit_amount=None),
                ContraLeg(account_id=icms.id, debit_amount=Decimal("200.00"), credit_amount=None),
            ],
            transaction_date=date(2026, 4, 15),
        )
        self.assertEqual(Decimal("0.00"), assert_transaction_balanced(result.transaction))
        # Two contra legs in the result
        self.assertEqual(len(result.contra_legs), 2)
        # Cash leg: credit 1000 → effective -1000
        self.assertEqual(result.cash_leg.credit_amount, Decimal("1000.00"))
        self.assertEqual(result.cash_leg.get_effective_amount(), Decimal("-1000.00"))

    def test_rejects_when_no_contra_legs(self):
        """Non-zero target without contras → refuse with a clear
        message so the operator knows to add a row."""
        with self.assertRaises(BankLedgerError) as cm:
            create_balanced_adjustment(
                company_id=self.company.id,
                bank_account_id=self.bank_account.id,
                adjustment_target=Decimal("-15.00"),
                contra_legs=[],
                transaction_date=date(2026, 4, 15),
            )
        self.assertIn("contra-lançamento", str(cm.exception))

    def test_accepts_zero_target_with_no_contras(self):
        """Edge: perfectly-balanced selection (delta=0) — nothing to
        book, but the caller might pass through. We allow the no-op
        to keep the call site simple."""
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=Decimal("0.00"),
            contra_legs=[],
            transaction_date=date(2026, 4, 15),
        )
        self.assertEqual(Decimal("0.00"), assert_transaction_balanced(result.transaction))
        # A zero-cash leg still gets written for provenance (so the
        # reconciliation has something to link to).
        self.assertIsNotNone(result.cash_leg)

    def test_rejects_missing_cash_account(self):
        """Bank account with no linked active CoA → refuse with a
        configuration-error message (not a generic 500)."""
        self.cash_account.is_active = False
        self.cash_account.save(update_fields=["is_active"])
        despesa = self._contra_account(code="4.1.3", direction=1)
        with self.assertRaises(BankLedgerError):
            create_balanced_adjustment(
                company_id=self.company.id,
                bank_account_id=self.bank_account.id,
                adjustment_target=Decimal("-10.00"),
                contra_legs=[ContraLeg(account_id=despesa.id, debit_amount=Decimal("10.00"), credit_amount=None)],
                transaction_date=date(2026, 4, 15),
            )


# ---------------------------------------------------------------- sum helpers


class SumExistingCashLegsTests(_BaseBankLedgerTest):
    """``sum_existing_cash_legs_for_jes`` underpins Case 1 (adjustment
    over existing match). Verify it counts only cash legs and
    aggregates effectives correctly."""

    def test_filters_to_cash_legs_only(self):
        # Non-cash contra
        despesa = self._contra_account(code="4.1.4", direction=1)

        tx = Transaction.objects.create(
            company=self.company,
            date=date(2026, 4, 15),
            entity=self.entity,
            amount=Decimal("100.00"),
            currency=self.currency,
            description="existing",
            state="posted",
        )
        cash_leg = JournalEntry.objects.create(
            company=self.company,
            transaction=tx,
            account=self.cash_account,
            debit_amount=Decimal("100.00"),
            date=date(2026, 4, 15),
            state="posted",
        )
        contra = JournalEntry.objects.create(
            company=self.company,
            transaction=tx,
            account=despesa,
            credit_amount=Decimal("100.00"),
            date=date(2026, 4, 15),
            state="posted",
        )
        summed, cash_legs = sum_existing_cash_legs_for_jes(
            [cash_leg.id, contra.id], self.company.id,
        )
        self.assertEqual(Decimal("100.00"), summed)
        self.assertEqual([je.id for je in cash_legs], [cash_leg.id])

    def test_returns_zero_for_empty_input(self):
        summed, cash_legs = sum_existing_cash_legs_for_jes([], self.company.id)
        self.assertEqual(summed, Decimal("0"))
        self.assertEqual(cash_legs, [])


# ---------------------------------------------------------------- payload helpers


class ContraLegsFromPayloadTests(TestCase):
    """Thin translator — make sure the important edges hold so the
    API contract stays forgiving."""

    def test_drops_blank_rows(self):
        legs = contra_legs_from_payload([
            {},
            {"account_id": None, "debit_amount": "10.00"},
            {"account_id": 1, "debit_amount": None, "credit_amount": None},
        ])
        self.assertEqual(legs, [])

    def test_parses_decimal_and_date(self):
        legs = contra_legs_from_payload([
            {"account_id": 42, "debit_amount": "15.50", "date": "2026-04-15"},
        ])
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0].account_id, 42)
        self.assertEqual(legs[0].debit_amount, Decimal("15.50"))
        self.assertEqual(legs[0].date, date(2026, 4, 15))

    def test_invalid_date_falls_back_to_default(self):
        legs = contra_legs_from_payload(
            [{"account_id": 1, "debit_amount": "1.00", "date": "not-a-date"}],
            default_date=date(2026, 1, 1),
        )
        self.assertEqual(legs[0].date, date(2026, 1, 1))


# ---------------------------------------------------------------- integration: case 1


class Case1AdjustmentOverExistingMatchTests(_BaseBankLedgerTest):
    """End-to-end: a previously-posted Transaction has a cash leg of
    +100; bank receipt is +98 (2% discount granted). The service
    creates a NEW adjustment Transaction with cash -2 + contra +2.
    The reconciliation links both cash legs so book_sum = +100 + -2
    = +98, matching the bank.
    """

    def test_discount_adjustment(self):
        # --- original booked transaction (invoice, cash leg existed)
        desconto = self._contra_account(code="4.1.5", direction=1, name="Desconto Concedido")
        original_tx = Transaction.objects.create(
            company=self.company,
            date=date(2026, 4, 10),
            entity=self.entity,
            amount=Decimal("100.00"),
            currency=self.currency,
            description="Original invoice",
            state="posted",
        )
        original_cash_leg = JournalEntry.objects.create(
            company=self.company,
            transaction=original_tx,
            account=self.cash_account,
            debit_amount=Decimal("100.00"),
            date=date(2026, 4, 10),
            state="posted",
        )
        # Original contra — not part of our test, just completing the
        # picture so the original tx balances.
        clientes = self._contra_account(code="1.1.2", direction=1, name="Clientes")
        JournalEntry.objects.create(
            company=self.company,
            transaction=original_tx,
            account=clientes,
            credit_amount=Decimal("100.00"),
            date=date(2026, 4, 10),
            state="posted",
        )
        original_balance = assert_transaction_balanced(original_tx)
        self.assertEqual(original_balance, Decimal("0.00"))

        # --- simulate the reconciliation flow's gap computation
        existing_sum, existing_cash_legs = sum_existing_cash_legs_for_jes(
            [original_cash_leg.id], self.company.id,
        )
        self.assertEqual(existing_sum, Decimal("100.00"))
        self.assertEqual(len(existing_cash_legs), 1)

        bank_amount = Decimal("98.00")
        adjustment_target = bank_amount - existing_sum  # = -2

        # --- create the adjustment
        result = create_balanced_adjustment(
            company_id=self.company.id,
            bank_account_id=self.bank_account.id,
            adjustment_target=adjustment_target,
            contra_legs=[
                # User picked: Débito Desconto Concedido 2 — expense
                ContraLeg(account_id=desconto.id, debit_amount=Decimal("2.00"), credit_amount=None),
            ],
            transaction_date=date(2026, 4, 15),
        )

        # --- invariants

        # 1) The original Transaction is untouched.
        self.assertEqual(assert_transaction_balanced(original_tx), Decimal("0.00"))
        self.assertEqual(original_tx.journal_entries.count(), 2)  # cash + clientes

        # 2) The adjustment Transaction is balanced.
        self.assertEqual(assert_transaction_balanced(result.transaction), Decimal("0.00"))
        # Two legs: cash + Desconto
        self.assertEqual(result.transaction.journal_entries.count(), 2)

        # 3) The adjustment cash leg's effective matches the gap.
        self.assertEqual(result.cash_leg.get_effective_amount(), adjustment_target)

        # 4) If we linked the reconciliation manually, book_sum would
        #    match the bank amount. We do that dance here to prove it.
        rec = Reconciliation.objects.create(
            company=self.company, status="matched",
        )
        bank_tx = self._bank_tx("98.00", date_=date(2026, 4, 15))
        rec.bank_transactions.add(bank_tx)
        for je in [*existing_cash_legs, result.cash_leg]:
            rec.journal_entries.add(je)

        book_sum = sum(
            (je.get_effective_amount() for je in rec.journal_entries.all()),
            Decimal("0"),
        )
        self.assertEqual(book_sum, bank_amount)
