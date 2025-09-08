# tests/test_payroll_integration.py

import unittest
import textwrap
from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from multitenancy.models import Company, CustomUser, IntegrationRule, IntegrationRuleLog, Entity
from accounting.models import Transaction, JournalEntry, Account, Currency
from multitenancy.formula_engine import execute_rule, trigger_rule_event
from hr.models import Employee, Position, Payroll, TimeTracking
from hr.serializers import PayrollSerializer, PayrollBulkStatusSerializer
from hr.views import PayrollViewSet

class TestPayrollIntegration(TestCase):
    """
    End-to-end tests to ensure:
     1) 'payroll_approved' triggers our integration rule,
     2) A Transaction is created in the accounting module,
     3) The bulk-update-status endpoint for payroll,
     4) Additional rules for 13th salary, vacation accrual, etc.
    """

    @classmethod
    def setUpTestData(cls):
        # 1) Setup minimal domain data

        # Create a sample Company
        cls.company = Company.objects.create(name="Test Company", subdomain="testco")
        cls.entity1 = Entity.objects.create(name="Entity 1", company=cls.company)
        cls.entity2 = Entity.objects.create(name="Entity 2", company=cls.company)

        # Create a user
        cls.user = CustomUser.objects.create_user(username="testuser", password="password123")

        # Create a Position
        cls.position = Position.objects.create(
            title="Developer",
            min_salary=2000,
            max_salary=5000
        )

        # Create two employees
        cls.employee = Employee.objects.create(
            CPF="123.456.789-00",
            name="Alice",
            position=cls.position,
            hire_date="2022-01-01",
            salary=3000,
            vacation_days=30,
            is_active=True
        )
        cls.employee2 = Employee.objects.create(
            CPF="987.654.321-00",
            name="Bob",
            position=cls.position,
            hire_date="2021-01-01",
            salary=4000,
            vacation_days=30,
            is_active=True
        )

        # Create or get a Currency for accounting
        cls.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$")

        # Create default Accounts if needed
        cls.account_cash = Account.objects.create(
            company=cls.company,
            account_code="CASH",
            name="Cash Account",
            type="asset",
            account_direction=1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        cls.account_salary = Account.objects.create(
            company=cls.company,
            account_code="SALARY",
            name="Salary Expense",
            type="expense",
            account_direction=1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        # Additional accounts for the tests below
        cls.account_vacation_expense = Account.objects.create(
            company=cls.company,
            account_code="VAC_EXP",
            name="Vacation Expense",
            type="expense",
            account_direction=1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        cls.account_vacation_liab = Account.objects.create(
            company=cls.company,
            account_code="VAC_LIAB",
            name="Vacation Liability",
            type="liability",
            account_direction=-1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        cls.account_13th_expense = Account.objects.create(
            company=cls.company,
            account_code="13TH_EXP",
            name="13th Salary Expense",
            type="expense",
            account_direction=1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        cls.account_13th_liab = Account.objects.create(
            company=cls.company,
            account_code="13TH_LIAB",
            name="13th Salary Liability",
            type="liability",
            account_direction=-1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )

        # 2) Create a sample IntegrationRule for "payroll_approved"
        cls.rule = IntegrationRule.objects.create(
            company=cls.company,
            name="Payroll Approved to Accounting",
            description="Creates a transaction when payroll is approved.",
            trigger_event="payroll_approved",
            is_active=True,
            rule=textwrap.dedent(f"""
debug_log("Rule triggered for payroll_approved")
transaction = create_transaction({{
    "date": "today()",
    "description": "'Payroll Approved'",
    "amount": "sum(float(item['gross_salary']) for item in payload)",
    "currency": {cls.currency.id},
    "company": {cls.company.id},
    "created_by": {cls.user.id}
}}, context)

je1 = create_journal_entry(transaction, {{
    "account": {cls.account_salary.id},
    "entity": {cls.entity1.id},
    "debit_amount": "sum(float(item['gross_salary']) for item in payload)",
    "credit_amount": 0
}}, context)

result = 'Rule triggered for payroll_approved'
""")
        )

        # 3) Create sample Payroll objects
        cls.payroll1 = Payroll.objects.create(
            company=cls.company,
            employee=cls.employee,
            pay_date="2025-01-01",
            gross_salary=3000,
            inss_deduction=0,
            irrf_deduction=0,
            fgts=0,
            net_salary=0,
            status=Payroll.STATUS_PENDING
        )
        cls.payroll2 = Payroll.objects.create(
            company=cls.company,
            employee=cls.employee2,
            pay_date="2025-01-01",
            gross_salary=4000,
            inss_deduction=0,
            irrf_deduction=0,
            fgts=0,
            net_salary=0,
            status=Payroll.STATUS_PENDING
        )

        # 4) Create IntegrationRules for the "vacation_accrual" and "13th_accrual" scenarios
        cls.rule_vacation_accrual = IntegrationRule.objects.create(
            company=cls.company,
            name="Vacation Monthly Accrual",
            description="Accrues monthly vacation expense and liability.",
            trigger_event="vacation_accrual_monthly",
            is_active=True,
            rule=textwrap.dedent(f"""
debug_log("Monthly Vacation Accrual triggered")

# Suppose 'payload' is a list of employees: [{{ 'salary': 3000 }}, ...]
total_accrual = 0.0
for emp in payload:
    # e.g. 2.5 days accrual => daily cost
    monthly = (float(emp['salary']) / 30.0) * 2.5
    total_accrual += monthly

transaction = create_transaction({{
    "date": "today()",
    "description": "'Vacation Accrual for month'",
    "amount": total_accrual,
    "currency": {cls.currency.id},
    "company": {cls.company.id},
    "created_by": {cls.user.id}
}}, context)

create_journal_entry(transaction, {{
    "account": {cls.account_vacation_expense.id},
    "entity": {cls.entity1.id},
    "debit_amount": total_accrual,
    "credit_amount": 0
}}, context)

create_journal_entry(transaction, {{
    "account": {cls.account_vacation_liab.id},
    "entity": {cls.entity1.id},
    "debit_amount": 0,
    "credit_amount": total_accrual
}}, context)

result = 'Vacation accrual done: ' + str(total_accrual)
""")
        )

        cls.rule_13th_accrual = IntegrationRule.objects.create(
            company=cls.company,
            name="13th Salary Accrual",
            description="Accrues monthly 13th salary expense and liability.",
            trigger_event="accrual_13th_monthly",
            is_active=True,
            rule=textwrap.dedent(f"""
debug_log("Monthly 13th Salary Accrual triggered")

total_13th = 0.0
for emp in payload:
    # 1/12 of monthly salary
    partial_13th = float(emp['salary']) / 12.0
    total_13th += partial_13th

transaction = create_transaction({{
    "date": "today()",
    "description": "'13th Salary Accrual'",
    "amount": total_13th,
    "currency": {cls.currency.id},
    "company": {cls.company.id},
    "created_by": {cls.user.id}
}}, context)

create_journal_entry(transaction, {{
    "account": {cls.account_13th_expense.id},
    "entity": {cls.entity1.id},
    "debit_amount": total_13th,
    "credit_amount": 0
}}, context)

create_journal_entry(transaction, {{
    "account": {cls.account_13th_liab.id},
    "entity": {cls.entity1.id},
    "debit_amount": 0,
    "credit_amount": total_13th
}}, context)

result = '13th accrual done: ' + str(total_13th)
""")
        )

        # 5) Create a "vacation payment" rule (just for demonstration)
        cls.rule_vacation_payment = IntegrationRule.objects.create(
            company=cls.company,
            name="Vacation Payment",
            description="Reverses vacation liability upon payment.",
            trigger_event="vacation_paid",
            is_active=True,
            rule=textwrap.dedent(f"""
debug_log("Vacation payment triggered")

pay_total = sum(float(r['vacation_pay']) for r in payload)

transaction = create_transaction({{
    "date": "today()",
    "description": "'Vacation Payment Payout'",
    "amount": pay_total,
    "currency": {cls.currency.id},
    "company": {cls.company.id},
    "created_by": {cls.user.id}
}}, context)

# Reverse the liability
create_journal_entry(transaction, {{
    "account": {cls.account_vacation_liab.id},
    "entity": {cls.entity1.id},
    "debit_amount": pay_total,
    "credit_amount": 0
}}, context)

# Credit cash or bank
create_journal_entry(transaction, {{
    "account": {cls.account_cash.id},
    "entity": {cls.entity1.id},
    "debit_amount": 0,
    "credit_amount": pay_total
}}, context)

result = 'Vacation paid: ' + str(pay_total)
""")
        )

    def setUp(self):
        """Runs before each test method."""
        self.client = APIClient()
        # Force the user so that 'auth.authenticate(...)' finds a user
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token MY_TEST_TOKEN')

    # ---------------------
    # Existing tests
    # ---------------------
    def test_bulk_update_to_approved_triggers_rule(self):
        """
        Calls POST /payroll/bulk-update-status with new_status='approved'
        and checks that the IntegrationRule is triggered, creating a Transaction.
        """
        url = reverse("payroll-bulk-update-status", kwargs={"tenant_id": self.company.subdomain})

        # We'll update both payroll1 and payroll2 to 'approved'
        request_payload = {
            "payroll_ids": [self.payroll1.id, self.payroll2.id],
            "new_status": Payroll.STATUS_APPROVED
        }

        response = self.client.post(url, request_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Refresh from DB
        self.payroll1.refresh_from_db()
        self.payroll2.refresh_from_db()
        self.assertEqual(self.payroll1.status, Payroll.STATUS_APPROVED)
        self.assertEqual(self.payroll2.status, Payroll.STATUS_APPROVED)

        # The rule should have triggered. Let's check the IntegrationRuleLog:
        logs = IntegrationRuleLog.objects.filter(rule=self.rule)
        self.assertTrue(logs.exists(), "Expected at least one log from the rule execution.")
        log = logs.last()
        self.assertTrue(log.success)
        self.assertIn("Rule triggered for payroll_approved", log.result)

        # Now let's see if a Transaction was created
        txn = Transaction.objects.first()
        self.assertIsNotNone(txn, "A Transaction should have been created by the rule.")
        # The rule sums 'salary' from each item => 3000 + 4000 = 7000
        self.assertEqual(float(txn.amount), 7000.0, "Should sum up the employees' salaries.")

        # Check that a JournalEntry was created
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je, "A JournalEntry should have been created by the rule.")
        self.assertEqual(float(je.debit_amount), 7000.0)
        self.assertEqual(float(je.credit_amount), 0.0)

    def test_rule_fires_directly(self):
        """
        Verify we can manually call trigger_rule_event('payroll_approved', payload)
        and the IntegrationRule creates a Transaction.
        """
        # Build a minimal payload: let's pretend these are dictionaries from the serializer
        payload_data = [
            {"id": self.payroll1.id, "gross_salary": 3000},
            {"id": self.payroll2.id, "gross_salary": 4000},
        ]
        trigger_rule_event(self.company.id, "payroll_approved", payload_data)

        # Check logs
        logs = IntegrationRuleLog.objects.filter(rule=self.rule)
        self.assertTrue(logs.exists())
        log = logs.last()
        self.assertTrue(log.success)
        self.assertIn("Rule triggered for payroll_approved", log.result)

        # Check transaction
        txn = Transaction.objects.first()
        self.assertIsNotNone(txn)
        self.assertEqual(float(txn.amount), 7000.0)

        # Journal Entry
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(float(je.debit_amount), 7000.0)
        self.assertEqual(float(je.credit_amount), 0.0)

    def test_generate_monthly_simulate(self):
        """
        Test that passing simulate=True to generate_monthly
        returns the would-be results without committing to DB.
        """
        url = reverse("payroll-generate-monthly", kwargs={"tenant_id": self.company.subdomain})

        request_payload = {
            "company_id": self.company.id,
            "employee_ids": [self.employee.id, self.employee2.id],
            "pay_date": "2025-02-01",
            "simulate": True
        }

        response = self.client.post(url, request_payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SIMULATION", response.data["message"])

        # Ensure no new Payroll was actually committed
        count = Payroll.objects.filter(pay_date="2025-02-01").count()
        self.assertEqual(count, 0, "No new payroll records should have been created on simulate mode.")

        # If the rule triggers, also check no new Transaction was committed
        txn_count = Transaction.objects.count()
        self.assertEqual(txn_count, 0, "No transaction should be created on simulate mode.")

    def test_bulk_update_approved_simulate(self):
        """
        Test that passing simulate=True to bulk-update-status does not commit changes or trigger final logs.
        """
        url = reverse("payroll-bulk-update-status", kwargs={"tenant_id": self.company.subdomain})
        request_payload = {
            "payroll_ids": [self.payroll1.id, self.payroll2.id],
            "new_status": Payroll.STATUS_APPROVED,
            "simulate": True
        }

        response = self.client.post(url, request_payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("SIMULATION", response.data["detail"])

        # Reload from DB
        self.payroll1.refresh_from_db()
        self.assertEqual(self.payroll1.status, Payroll.STATUS_PENDING, "Status should remain pending because simulate=True.")

        # And no transaction or logs
        self.assertFalse(Transaction.objects.exists(), "No transactions should exist in simulate mode.")
        self.assertFalse(IntegrationRuleLog.objects.exists(), "No logs should be created in simulate mode.")

    # ------------------------
    # New tests for Vacation & 13th Accrual
    # ------------------------
    def test_monthly_vacation_accrual_rule_success(self):
        """
        Test the 'vacation_accrual_monthly' rule (IntegrationRule) works and creates a transaction + 2 JEs.
        """
        # Setup a short payload: employees with salaries
        employees_data = [
            {"id": self.employee.id, "salary": "3000.00"},
            {"id": self.employee2.id, "salary": "4000.00"}
        ]

        # Trigger
        trigger_rule_event(self.company.id, "vacation_accrual_monthly", employees_data)

        # Check the log
        rule_obj = IntegrationRule.objects.get(name="Vacation Monthly Accrual")
        logs = IntegrationRuleLog.objects.filter(rule=rule_obj)
        self.assertTrue(logs.exists(), "Vacation accrual rule should have a log.")
        log = logs.last()
        self.assertTrue(log.success)
        self.assertIn("Vacation accrual done:", log.result)

        # Check the transaction
        txn = Transaction.objects.last()  # the newly created transaction
        self.assertIsNotNone(txn)
        # 2.5 days => monthly cost: (3000/30)*2.5=250.0, (4000/30)*2.5=333.33..., total ~583.33
        # For test simplicity, we can just check it's around 583.33:
        self.assertAlmostEqual(float(txn.amount), 583.33, places=1)

        # Should have 2 JEs (exp + liab)
        jes = JournalEntry.objects.filter(transaction=txn)
        self.assertEqual(jes.count(), 2)

    def test_monthly_13th_accrual_rule_success(self):
        """
        Test the 'accrual_13th_monthly' rule. 1/12 per month of each employee's salary
        """
        employees_data = [
            {"id": self.employee.id, "salary": "3000.00"},
            {"id": self.employee2.id, "salary": "4000.00"}
        ]
        # Trigger
        trigger_rule_event(self.company.id, "accrual_13th_monthly", employees_data)

        rule_obj = IntegrationRule.objects.get(name="13th Salary Accrual")
        logs = IntegrationRuleLog.objects.filter(rule=rule_obj)
        self.assertTrue(logs.exists())
        log = logs.last()
        self.assertTrue(log.success)
        self.assertIn("13th accrual done:", log.result)

        # (3000 / 12)=250, (4000 / 12)=333.33 => total ~583.33
        txn = Transaction.objects.last()
        self.assertIsNotNone(txn)
        self.assertAlmostEqual(float(txn.amount), 583.33, places=1)
        # 2 JEs => DR 13th Expense, CR 13th Liability
        jes = JournalEntry.objects.filter(transaction=txn)
        self.assertEqual(jes.count(), 2)

    def test_vacation_payment_rule_success(self):
        """
        Suppose we pay out vacation to Bob. The rule reverses the liability and credits cash.
        """
        # We pass in a payload e.g. [ {"vacation_pay": 1000}, ... ]
        payload_data = [
            {"employee_id": self.employee2.id, "vacation_pay": "1200.00"}
        ]
        trigger_rule_event(self.company.id, "vacation_paid", payload_data)

        rule_obj = IntegrationRule.objects.get(name="Vacation Payment")
        logs = IntegrationRuleLog.objects.filter(rule=rule_obj)
        self.assertTrue(logs.exists())
        log = logs.last()
        self.assertTrue(log.success)
        self.assertIn("Vacation paid: 1200.0", log.result)

        txn = Transaction.objects.last()
        self.assertIsNotNone(txn)
        self.assertEqual(float(txn.amount), 1200.0)

        # Journal Entries => DR Vacation Liability, CR Cash
        jes = JournalEntry.objects.filter(transaction=txn)
        self.assertEqual(jes.count(), 2)
        je_dr = jes.get(debit_amount__gt=0)
        je_cr = jes.get(credit_amount__gt=0)
        self.assertAlmostEqual(float(je_dr.debit_amount), 1200.0)
        self.assertAlmostEqual(float(je_cr.credit_amount), 1200.0)

    def test_accrual_rule_with_invalid_syntax(self):
        """
        Example of a failure scenario: if the rule snippet has a syntax error.
        We'll create a rule with invalid code, then call the event.
        We'll confirm IntegrationRuleLog has success=False, error message in result.
        """
        # Create a broken rule
        broken_rule = IntegrationRule.objects.create(
            company=self.company,
            name="Broken 13th Accrual",
            trigger_event="broken_13th_accrual",
            is_active=True,
            rule="debug_log('This is broken rule' # missing a parenthesis or something"
        )

        employees_data = [
            {"id": self.employee.id, "salary": "3000.00"},
        ]
        # Trigger
        trigger_rule_event(self.company.id, "broken_13th_accrual", employees_data)

        log = IntegrationRuleLog.objects.filter(rule=broken_rule).last()
        self.assertIsNotNone(log)
        self.assertFalse(log.success, "Should fail due to syntax error")
        self.assertIn("Syntax Error in rule:", (log.result or ""))

    def test_accrual_rule_runtime_error(self):
        """
        Another failure: we do have valid syntax but we refer to something undefined => runtime error
        """
        # We'll create a rule that references a variable 'emp['not_a_field']'
        runtime_error_rule = IntegrationRule.objects.create(
            company=self.company,
            name="Runtime Error Accrual",
            trigger_event="runtime_error_accrual",
            is_active=True,
            rule=textwrap.dedent("""
debug_log("Starting runtime error rule")
some_total = 0
for emp in payload:
    some_total += float(emp['not_a_field']) # doesn't exist => KeyError
result = "Should never get here"
""")
        )

        employees_data = [
            {"id": self.employee.id, "salary": "3000.00"},
        ]
        # Trigger
        trigger_rule_event(self.company.id, "runtime_error_accrual", employees_data)

        log = IntegrationRuleLog.objects.filter(rule=runtime_error_rule).last()
        self.assertIsNotNone(log)
        self.assertFalse(log.success)
        self.assertIn("not_a_field", (log.result or ""), "Should mention KeyError in the log")

if __name__ == "__main__":
    unittest.main()
