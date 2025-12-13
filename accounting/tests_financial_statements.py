"""
Test for Financial Statements Report

This test uses datbaby data to:
1. Run template generation in preview mode (financial statement template id=3)
2. Review the expected output from the template against the used accounts summarized by month (sum)
"""

from django.test import TestCase
from django.db.models import Q, Sum, F
from django.db.models.functions import TruncMonth
from decimal import Decimal
from datetime import date
from collections import defaultdict

from multitenancy.models import Company
from accounting.models import Account, JournalEntry, Currency
from accounting.models_financial_statements import FinancialStatementTemplate, FinancialStatementLineTemplate
from accounting.services.financial_statement_service import FinancialStatementGenerator
from accounting.utils_time_dimensions import generate_periods


class FinancialStatementReportTest(TestCase):
    """
    Test financial statement report generation using datbaby data.
    
    This test:
    1. Uses datbaby company data (company_id=4)
    2. Runs template generation in preview mode for template id=3
    3. Compares the template output against accounts summarized by month
    """
    
    @classmethod
    def setUpTestData(cls):
        """Set up test data - assumes datbaby data is already loaded in the database."""
        # Datbaby company ID
        cls.company_id = 4
        
        # Verify company exists
        try:
            cls.company = Company.objects.get(id=cls.company_id)
        except Company.DoesNotExist:
            # Will be checked in setUp
            cls.company = None
        
        # Get template id=3
        try:
            cls.template = FinancialStatementTemplate.objects.get(
                id=3,
                company_id=cls.company_id
            )
        except FinancialStatementTemplate.DoesNotExist:
            # Will be checked in setUp
            cls.template = None
        
        # Get currency (usually there's at least one)
        cls.currency = Currency.objects.first()
    
    def setUp(self):
        """Check prerequisites before each test."""
        if not self.company:
            self.skipTest(f"Company with id={self.company_id} (datbaby) not found. Please load datbaby data first.")
        
        if not self.template:
            self.skipTest(f"Financial statement template with id=3 not found for company {self.company_id}")
        
        if not self.currency:
            self.skipTest("No currency found in database")
    
    def test_financial_statement_preview_vs_account_summary(self):
        """
        Test that financial statement preview output matches account summaries by month.
        
        Steps:
        1. Generate preview for template id=3
        2. Get all accounts used in the template
        3. Summarize those accounts by month (sum of journal entries)
        4. Compare template line values against account summaries
        """
        # Define date range - use a reasonable range for testing
        # You may want to adjust this based on your datbaby data
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        
        # Step 1: Generate preview
        generator = FinancialStatementGenerator(company_id=self.company_id)
        preview_data = generator.preview_statement(
            template=self.template,
            start_date=start_date,
            end_date=end_date,
            currency_id=self.currency.id if self.currency else None,
            include_pending=False,
        )
        
        self.assertIsNotNone(preview_data, "Preview data should not be None")
        self.assertIn('lines', preview_data, "Preview data should contain 'lines'")
        
        # Step 2: Get all accounts used in the template
        line_templates = self.template.line_templates.all().order_by('line_number')
        all_account_ids = set()
        account_by_line = {}
        
        for line_template in line_templates:
            accounts = generator._get_accounts_for_line(line_template)
            account_ids = [acc.id for acc in accounts]
            all_account_ids.update(account_ids)
            account_by_line[line_template.line_number] = {
                'accounts': accounts,
                'account_ids': account_ids,
                'line_template': line_template,
            }
        
        # Step 3: Summarize accounts by month
        # Get journal entries for all accounts in the date range
        journal_entries = JournalEntry.objects.filter(
            account_id__in=all_account_ids,
            transaction__company_id=self.company_id,
            state='posted',
        ).filter(
            Q(date__gte=start_date, date__lte=end_date) |
            Q(date__isnull=True, transaction__date__gte=start_date, transaction__date__lte=end_date)
        )
        
        # Group by account and month, then sum
        account_monthly_summary = defaultdict(lambda: defaultdict(Decimal))
        
        # Annotate with month
        entries_by_month = journal_entries.annotate(
            month=TruncMonth('date')
        ).values('account_id', 'month').annotate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        ).order_by('account_id', 'month')
        
        # Build summary dictionary
        for entry in entries_by_month:
            account_id = entry['account_id']
            month_key = entry['month'].strftime('%Y-%m') if entry['month'] else 'unknown'
            debit = entry['total_debit'] or Decimal('0.00')
            credit = entry['total_credit'] or Decimal('0.00')
            
            # Get account to apply direction
            try:
                account = Account.objects.get(id=account_id)
                # Calculate net movement: (debit - credit) * account_direction
                net_movement = (debit - credit) * account.account_direction
                account_monthly_summary[account_id][month_key] = net_movement
            except Account.DoesNotExist:
                # Account doesn't exist, skip
                continue
        
        # Step 4: Compare template output against account summaries
        # Generate periods for comparison
        periods = generate_periods(start_date, end_date, 'month')
        period_by_key = {p['key']: p for p in periods}
        
        # For each line in the template, compare against account summaries
        comparison_results = []
        
        for line_data in preview_data['lines']:
            line_number = line_data['line_number']
            line_label = line_data['label']
            line_balance = Decimal(str(line_data['balance']))
            line_type = line_data['line_type']
            
            # Skip headers and spacers
            if line_type in ('header', 'spacer'):
                continue
            
            # Get accounts for this line
            if line_number not in account_by_line:
                continue
            
            line_info = account_by_line[line_number]
            line_accounts = line_info['accounts']
            line_template = line_info['line_template']
            
            # Calculate expected value from account summaries for the full period
            expected_total = Decimal('0.00')
            monthly_breakdown = {}
            
            for account in line_accounts:
                account_monthly_totals = account_monthly_summary.get(account.id, {})
                
                # Sum all months for this account
                account_total = sum(account_monthly_totals.values(), Decimal('0.00'))
                expected_total += account_total
                
                # Store monthly breakdown
                monthly_breakdown[account.id] = {
                    'account_name': account.name,
                    'account_code': account.account_code,
                    'monthly_totals': dict(account_monthly_totals),
                    'total': account_total,
                }
            
            # Compare (allow small tolerance for rounding differences)
            tolerance = Decimal('0.01')
            difference = abs(line_balance - expected_total)
            
            comparison_results.append({
                'line_number': line_number,
                'line_label': line_label,
                'template_value': float(line_balance),
                'expected_value': float(expected_total),
                'difference': float(difference),
                'matches': difference <= tolerance,
                'account_count': len(line_accounts),
                'calculation_type': line_template.calculation_type,
                'monthly_breakdown': monthly_breakdown,
            })
        
        # Assertions
        mismatches = [r for r in comparison_results if not r['matches']]
        
        if mismatches:
            # Print detailed comparison for debugging
            print("\n" + "="*80)
            print("FINANCIAL STATEMENT COMPARISON RESULTS")
            print("="*80)
            print(f"Template: {self.template.name} (ID: {self.template.id})")
            print(f"Period: {start_date} to {end_date}")
            print(f"Total lines compared: {len(comparison_results)}")
            print(f"Mismatches: {len(mismatches)}")
            print("\n" + "-"*80)
            
            for result in comparison_results:
                status = "✓" if result['matches'] else "✗"
                print(f"\n{status} Line {result['line_number']}: {result['line_label']}")
                print(f"  Template Value: {result['template_value']:,.2f}")
                print(f"  Expected Value: {result['expected_value']:,.2f}")
                print(f"  Difference: {result['difference']:,.2f}")
                print(f"  Calculation Type: {result['calculation_type']}")
                print(f"  Accounts Used: {result['account_count']}")
                
                if not result['matches']:
                    print(f"  Monthly Breakdown:")
                    for account_id, breakdown in result['monthly_breakdown'].items():
                        print(f"    Account: {breakdown['account_code']} - {breakdown['account_name']}")
                        print(f"      Total: {breakdown['total']:,.2f}")
                        if breakdown['monthly_totals']:
                            for month, value in sorted(breakdown['monthly_totals'].items()):
                                print(f"        {month}: {value:,.2f}")
            
            print("\n" + "="*80)
        
        # Assert that all lines match (within tolerance)
        # Note: Some lines might use formulas or different calculation methods,
        # so we'll report mismatches but allow the test to pass with warnings
        self.assertTrue(
            len(mismatches) == 0,
            f"Found {len(mismatches)} line(s) with mismatched values. "
            f"See output above for details. "
            f"This might be expected for formula-based lines or different calculation types."
        )
    
    def test_financial_statement_monthly_breakdown(self):
        """
        Test that we can generate monthly breakdowns for the financial statement.
        
        This test generates a time series preview and compares it against
        account summaries by month.
        """
        start_date = date(2025, 1, 1)
        end_date = date(2025, 12, 31)
        
        generator = FinancialStatementGenerator(company_id=self.company_id)
        
        # Generate time series preview (monthly)
        time_series = generator.preview_time_series(
            template=self.template,
            start_date=start_date,
            end_date=end_date,
            dimension='month',
            include_pending=False,
        )
        
        self.assertIsNotNone(time_series, "Time series should not be None")
        self.assertIn('lines', time_series, "Time series should contain 'lines'")
        self.assertEqual(time_series['dimension'], 'month', "Dimension should be 'month'")
        
        # Get all accounts used in template
        line_templates = self.template.line_templates.all().order_by('line_number')
        all_account_ids = set()
        account_by_line = {}
        
        for line_template in line_templates:
            accounts = generator._get_accounts_for_line(line_template)
            account_ids = [acc.id for acc in accounts]
            all_account_ids.update(account_ids)
            account_by_line[line_template.line_number] = {
                'accounts': accounts,
                'account_ids': account_ids,
            }
        
        # Generate account summaries by month
        journal_entries = JournalEntry.objects.filter(
            account_id__in=all_account_ids,
            transaction__company_id=self.company_id,
            state='posted',
        ).filter(
            Q(date__gte=start_date, date__lte=end_date) |
            Q(date__isnull=True, transaction__date__gte=start_date, transaction__date__lte=end_date)
        )
        
        # Group by account and month
        account_monthly_summary = defaultdict(lambda: defaultdict(Decimal))
        
        entries_by_month = journal_entries.annotate(
            month=TruncMonth('date')
        ).values('account_id', 'month').annotate(
            total_debit=Sum('debit_amount'),
            total_credit=Sum('credit_amount')
        ).order_by('account_id', 'month')
        
        for entry in entries_by_month:
            account_id = entry['account_id']
            month_key = entry['month'].strftime('%Y-%m') if entry['month'] else 'unknown'
            debit = entry['total_debit'] or Decimal('0.00')
            credit = entry['total_credit'] or Decimal('0.00')
            
            try:
                account = Account.objects.get(id=account_id)
                net_movement = (debit - credit) * account.account_direction
                account_monthly_summary[account_id][month_key] = net_movement
            except Account.DoesNotExist:
                continue
        
        # Compare time series values against account summaries for each month
        for line_data in time_series['lines']:
            line_number = line_data['line_number']
            line_label = line_data['label']
            
            if line_data['line_type'] in ('header', 'spacer'):
                continue
            
            if line_number not in account_by_line:
                continue
            
            line_accounts = account_by_line[line_number]['accounts']
            
            # For each month in the time series
            for period_data in line_data['data']:
                month_key = period_data['period_key']
                template_value = Decimal(str(period_data['value']))
                
                # Calculate expected value from account summaries for this month
                expected_value = Decimal('0.00')
                for account in line_accounts:
                    monthly_total = account_monthly_summary.get(account.id, {}).get(month_key, Decimal('0.00'))
                    expected_value += monthly_total
                
                # Compare (with tolerance)
                tolerance = Decimal('0.01')
                difference = abs(template_value - expected_value)
                
                self.assertTrue(
                    difference <= tolerance,
                    f"Line {line_number} ({line_label}) for month {month_key}: "
                    f"template value {template_value} != expected {expected_value} "
                    f"(difference: {difference})"
                )

