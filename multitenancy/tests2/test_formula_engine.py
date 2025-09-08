import unittest
import ast
import textwrap
import time

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError

# Models
from accounting.models import Transaction, JournalEntry, Account, Currency
from multitenancy.models import Company, CustomUser, Entity

# Formula Engine
from multitenancy.formula_engine import (
    create_transaction,
    create_journal_entry,
    evaluate_expression,
    FormulaEvaluationError,
    sum_group,
    max_group,
    min_group,
    group_by,
    TimeoutException,
    timeout_handler,
    execute_rule,
)


class TestFormulaEngineRealLife(TestCase):
    """
    Real-life scenarios for transaction and journal entry creation with grouping,
    starting with smaller, simpler tests, then expanding to full multi-line rules.
    """

    @classmethod
    def setUpTestData(cls):
        # Common setup for all tests
        cls.company = Company.objects.create(name="Test Company", subdomain="testco")
        cls.user = CustomUser.objects.create_user(username="testuser", password="password123")
        cls.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$")
        cls.entity1 = Entity.objects.create(name="Entity 1", company=cls.company)
        cls.entity2 = Entity.objects.create(name="Entity 2", company=cls.company)

        cls.account_salary = Account.objects.create(
            company=cls.company,
            account_code="SALARY",
            name="Salary Account",
            type="expense",
            account_direction=1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )
        cls.account_tax = Account.objects.create(
            company=cls.company,
            account_code="TAX",
            name="Tax Account",
            type="liability",
            account_direction=-1,
            balance=0,
            currency=cls.currency,
            is_active=True
        )

        cls.payload = [
            {"employee": "Alice", "department": "HR", "base_salary": 3000, "tax": 300},
            {"employee": "Bob", "department": "Finance", "base_salary": 4000, "tax": 400},
            {"employee": "Charlie", "department": "HR", "base_salary": 3500, "tax": 350},
        ]

    # --------------------------------------------------------------------------
    # 1) SMALLER TESTS TO PINPOINT ISSUES BEFORE MULTI-LINE RULES
    # --------------------------------------------------------------------------

    def test_minimal_no_op_rule(self):
        """
        Minimal test to ensure we can run a do-nothing rule that just sets result.
        This verifies that execute_rule() and the context are basically okay.
        """
        print("\n=== TEST: test_minimal_no_op_rule ===")

        rule = textwrap.dedent("""
debug_log("DEBUG in rule: minimal no-op")
result = True
        """)
        print("DEBUG final rule:\n", repr(rule))
        # Just a trivial rule, no references to payload, etc.

        execute_rule(self.company.id, rule, self.payload)
        # If we get here with no errors, we're good.

    def test_create_transaction_minimal(self):
        """
        Test calling create_transaction directly with static fields,
        no generator expressions or advanced logic.
        """
        print("\n=== TEST: test_create_transaction_minimal ===")

        # A minimal context with no references to 'payload'
        context = {
            "static_amt": 1000,
            "desc": "Simple Transaction"
        }

        transaction_template = {
            "date": "today()",
            "description": "'Created: ' + desc",
            "amount": "static_amt",
            "currency": self.currency.id,    # pass ID directly, not a string expression
            "company": self.company.id,
            "created_by": self.user.id
        }

        transaction = create_transaction(transaction_template, context)
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.description, "Created: Simple Transaction")
        self.assertEqual(float(transaction.amount), 1000.0)

    def test_create_transaction_with_sum_group(self):
        """
        Test calling create_transaction with a sum_group expression referencing 'payload'.
        This does not use the rule exec, but does test the aggregator logic.
        """
        print("\n=== TEST: test_create_transaction_with_sum_group ===")

        # We'll put 'payload' in context, though not absolutely required
        context = {
            "payload": self.payload
        }

        # sum_group(payload, 'base_salary') => 3000+4000+3500=10500
        transaction_template = {
            "date": "today()",
            "description": "'Salary Summation'",
            "amount": "sum_group(payload, 'base_salary')",  # reference aggregator
            "currency": self.currency.id,
            "company": self.company.id,
            "created_by": self.user.id
        }

        transaction = create_transaction(transaction_template, context)
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.description, "Salary Summation")
        # base_salary total = 10500
        self.assertEqual(float(transaction.amount), 10500.0)

    def test_create_transaction_with_generator_expression(self):
        """
        Test create_transaction with a generator expression:
        sum(item['base_salary'] for item in payload)
        Again, called directly, not via a multi-line rule.
        """
        print("\n=== TEST: test_create_transaction_with_generator_expression ===")

        context = {
            "payload": self.payload
        }

        transaction_template = {
            "date": "today()",
            "description": "'Generator Expression Test'",
            "amount": "sum(item['base_salary'] for item in payload)",
            "currency": self.currency.id,
            "company": self.company.id,
            "created_by": self.user.id
        }

        transaction = create_transaction(transaction_template, context)
        self.assertIsNotNone(transaction)
        self.assertEqual(transaction.description, "Generator Expression Test")
        # sum of base_salary = 10500
        self.assertEqual(float(transaction.amount), 10500.0)

    # --------------------------------------------------------------------------
    # 2) FULL-SCENARIO TESTS: MULTILINE RULES USING EXEC, ETC.
    # --------------------------------------------------------------------------
    def test_single_transaction_with_grouped_journal_entries(self):
        """Group all payloads into one transaction, group journal entries by account."""
        print("\n=== TEST: test_single_transaction_with_grouped_journal_entries ===")

        # The multi-line rule string
        rule = f"""
debug_log("DEBUG in rule: starting Scenario 1")
# Create a single transaction for all employees
transaction = create_transaction({{
    "date": "today()",
    "description": "'Payroll for all employees'",
    "amount": "sum(item['base_salary'] + item['tax'] for item in payload)",
    "currency": {self.currency.id},
    "company": {self.company.id},
    "created_by": {self.user.id}
}}, context)

if transaction is None:
    raise ValueError("Transaction creation failed.")

# Create journal entries grouped by account
je1 = create_journal_entry(transaction, {{
    "account": {self.account_salary.id},
    "entity": {self.entity1.id},
    "debit_amount": "sum(item['base_salary'] for item in payload)",
    "credit_amount": 0
}}, context)

je2 = create_journal_entry(transaction, {{
    "account": {self.account_tax.id},
    "entity": {self.entity2.id},
    "debit_amount": 0,
    "credit_amount": "sum(item['tax'] for item in payload)"
}}, context)

debug_log("DEBUG in rule: transaction=", transaction, "je1=", je1, "je2=", je2)

# Final step: set result
result = True
"""

        # Debug: show the final rule
        print("\n[DEBUG] Final multiline rule:\n", rule)
        print("\n[DEBUG] Attempting to parse the rule with ast.parse()...")

        # Just to ensure the rule is valid Python syntax from our end:
        ast_parsed = ast.parse(rule)
        print("[DEBUG] Successfully parsed the rule. AST:\n", ast.dump(ast_parsed, indent=2))

        # Now we run it in the sandbox
        execute_rule(self.company.id, rule, self.payload)

        # After it completes, let's do our checks
        transaction = Transaction.objects.first()
        self.assertIsNotNone(transaction)

        # base salaries: 3000+4000+3500=10500; taxes: 300+400+350=1050 => total=11550
        self.assertEqual(float(transaction.amount), 11550.0)  
        self.assertEqual(JournalEntry.objects.count(), 2)

    def test_transactions_grouped_by_department(self):
        """Create one transaction per department and journal entries per employee."""
        print("\n=== TEST: test_transactions_grouped_by_department ===")

        rule = f"""
debug_log("DEBUG in rule: starting Scenario 2")
# Group transactions by department
grouped = group_by(payload, 'department')

for group in grouped:
    debug_log('🔄 Processing group:', group['group'])
    context["group"] = group
    transaction = create_transaction({{
        "date": "today()",
        "description": "'Payroll for ' + group['group'] + ' department'",
        "amount": "sum(item['base_salary'] + item['tax'] for item in group['items'])",
        "currency": {self.currency.id},
        "company": {self.company.id},
        "created_by": {self.user.id}
    }}, context)

    if transaction is None:
        raise ValueError(f"Transaction creation failed for department")

    for item in group['items']:
        create_journal_entry(transaction, {{
            "account": {self.account_salary.id},
            "entity": {self.entity1.id},
            "debit_amount": item['base_salary'],
            "credit_amount": 0
        }}, context)

        create_journal_entry(transaction, {{
            "account": {self.account_tax.id},
            "entity": {self.entity2.id},
            "debit_amount": 0,
            "credit_amount": item['tax']
        }}, context)

debug_log("DEBUG in rule: finishing Scenario 2")

# Final step: set result
result = True
"""

        # Print the final rule for debugging
        print("\n[DEBUG] Final multiline rule (Scenario 2):\n", rule)
        print("\n[DEBUG] Attempting to parse the rule with ast.parse()...")

        # Ensure valid Python syntax
        ast_parsed = ast.parse(rule)
        print("[DEBUG] Successfully parsed the rule (Scenario 2). AST:\n", ast.dump(ast_parsed, indent=2))

        # Execute
        execute_rule(self.company.id, rule, self.payload)

        # Validations
        self.assertEqual(Transaction.objects.count(), 2)  # HR and Finance
        # 3 employees × 2 entries each = 6
        self.assertEqual(JournalEntry.objects.count(), 6)


    def test_substitution_rule(self):
            """Test the application of substitution rules."""
            from multitenancy.models import SubstitutionRule
    
            SubstitutionRule.objects.create(
                company=self.company,
                model_name="Employee",
                field_name="department",
                match_type="exact",
                match_value="HR",
                substitution_value="Human Resources"
            )
    
            rule = """
apply_substitutions("Employee", fields=["department"])
result = payload
    """
            result = execute_rule(self.company.id, rule, self.payload)
    
            self.assertEqual(result[0]["department"], "Human Resources")

    

if __name__ == "__main__":
    unittest.main()
