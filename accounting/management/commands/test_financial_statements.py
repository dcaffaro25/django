"""
Management command to test financial statement generation and debug parent account calculations.

Usage:
    python manage.py test_financial_statements --company-id 1 --create-template
    python manage.py test_financial_statements --company-id 1 --template-id 1 --preview
    python manage.py test_financial_statements --company-id 1 --template-id 1 --preview --start-date 2025-01-01 --end-date 2025-12-31
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum
from decimal import Decimal
from datetime import date, datetime
import json

from accounting.models import Account, JournalEntry, Currency
from accounting.models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
)
from accounting.services.financial_statement_service import FinancialStatementGenerator


class Command(BaseCommand):
    help = 'Test financial statement generation and debug parent account calculations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            required=True,
            help='Company ID to test with'
        )
        parser.add_argument(
            '--create-template',
            action='store_true',
            help='Create a test template for parent account debugging'
        )
        parser.add_argument(
            '--template-id',
            type=int,
            help='Template ID to use for preview'
        )
        parser.add_argument(
            '--preview',
            action='store_true',
            help='Generate a preview of the financial statement'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD)',
            default=None
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD)',
            default=None
        )
        parser.add_argument(
            '--as-of-date',
            type=str,
            help='As of date for balance sheet (YYYY-MM-DD)',
            default=None
        )
        parser.add_argument(
            '--include-pending',
            action='store_true',
            help='Include pending journal entries'
        )
        parser.add_argument(
            '--debug-accounts',
            action='store_true',
            help='Show detailed account calculation debugging'
        )
        parser.add_argument(
            '--list-templates',
            action='store_true',
            help='List all available templates for the company'
        )
        parser.add_argument(
            '--list-parent-accounts',
            action='store_true',
            help='List all parent accounts and their children'
        )

    def handle(self, *args, **options):
        company_id = options['company_id']
        
        # List templates
        if options['list_templates']:
            self.list_templates(company_id)
            return
        
        # List parent accounts
        if options['list_parent_accounts']:
            self.list_parent_accounts(company_id)
            return
        
        # Create test template
        if options['create_template']:
            self.create_test_template(company_id)
            return
        
        # Generate preview
        if options['preview']:
            if not options['template_id']:
                raise CommandError('--template-id is required for preview')
            
            template_id = options['template_id']
            start_date = self.parse_date(options['start_date']) if options['start_date'] else date.today().replace(month=1, day=1)
            end_date = self.parse_date(options['end_date']) if options['end_date'] else date.today()
            as_of_date = self.parse_date(options['as_of_date']) if options['as_of_date'] else end_date
            include_pending = options['include_pending']
            debug_accounts = options['debug_accounts']
            
            self.generate_preview(
                company_id,
                template_id,
                start_date,
                end_date,
                as_of_date,
                include_pending,
                debug_accounts
            )
            return
        
        self.stdout.write(self.style.ERROR('No action specified. Use --create-template, --preview, --list-templates, or --list-parent-accounts'))
    
    def parse_date(self, date_str):
        """Parse date string in YYYY-MM-DD format."""
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError(f'Invalid date format: {date_str}. Use YYYY-MM-DD')
    
    def list_templates(self, company_id):
        """List all financial statement templates for the company."""
        templates = FinancialStatementTemplate.objects.filter(
            company_id=company_id
        ).order_by('report_type', 'name')
        
        if not templates.exists():
            self.stdout.write(self.style.WARNING('No templates found for company %s' % company_id))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nFinancial Statement Templates (Company {company_id}):\n'))
        self.stdout.write(f'{"ID":<6} {"Name":<40} {"Type":<20} {"Active":<8} {"Default":<8} {"Lines":<8}')
        self.stdout.write('-' * 90)
        
        for template in templates:
            line_count = template.line_templates.count()
            active = 'Yes' if template.is_active else 'No'
            default = 'Yes' if template.is_default else 'No'
            self.stdout.write(
                f'{template.id:<6} {template.name:<40} {template.get_report_type_display():<20} '
                f'{active:<8} {default:<8} {line_count:<8}'
            )
    
    def list_parent_accounts(self, company_id):
        """List all parent accounts and their children with balances."""
        accounts = Account.objects.filter(company_id=company_id).order_by('account_code')
        parent_accounts = [acc for acc in accounts if not acc.is_leaf()]
        
        if not parent_accounts:
            self.stdout.write(self.style.WARNING('No parent accounts found for company %s' % company_id))
            return
        
        self.stdout.write(self.style.SUCCESS(f'\nParent Accounts (Company {company_id}):\n'))
        
        for parent in parent_accounts:
            all_children = parent.get_children()
            children = all_children.filter(company_id=company_id)
            self.stdout.write(f'\n{parent.account_code} - {parent.name} (ID: {parent.id})')
            self.stdout.write(f'  Path: {parent.get_path()}')
            self.stdout.write(f'  Company ID: {parent.company_id}')
            self.stdout.write(f'  Stored Balance: {parent.balance}')
            self.stdout.write(f'  Balance Date: {parent.balance_date}')
            self.stdout.write(f'  Total Children: {all_children.count()}')
            self.stdout.write(f'  Children (company {company_id}): {children.count()}')
            
            if all_children.exists() and not children.exists():
                self.stdout.write(self.style.ERROR(
                    f'  ⚠ WARNING: All {all_children.count()} children belong to different companies!'
                ))
                for child in all_children[:3]:  # Show first 3
                    self.stdout.write(f'    - {child.account_code} (Company ID: {child.company_id})')
            
            if children.exists():
                self.stdout.write('  Child Accounts:')
                total_children_balance = Decimal('0.00')
                for child in children:
                    child_balance = child.get_current_balance()
                    total_children_balance += child_balance
                    is_leaf = '✓' if child.is_leaf() else '✗'
                    self.stdout.write(
                        f'    [{is_leaf}] {child.account_code} - {child.name} '
                        f'(ID: {child.id}): {child_balance}'
                    )
                
                self.stdout.write(f'  Sum of Children Balances: {total_children_balance}')
                self.stdout.write(f'  Difference: {parent.balance - total_children_balance}')
    
    def create_test_template(self, company_id):
        """Create a test template specifically for debugging parent account calculations."""
        # Get currency
        currency = Currency.objects.filter(
            accounts__company_id=company_id
        ).first() or Currency.objects.first()
        
        if not currency:
            raise CommandError('No currency found. Please create a currency first.')
        
        # Get some parent accounts to test
        accounts = Account.objects.filter(company_id=company_id)
        parent_accounts = [acc for acc in accounts if not acc.is_leaf()][:5]  # Get first 5 parent accounts
        
        if not parent_accounts:
            self.stdout.write(self.style.WARNING('No parent accounts found. Creating a generic test template.'))
        
        # Create template
        template, created = FinancialStatementTemplate.objects.get_or_create(
            company_id=company_id,
            name='Parent Account Test Template',
            defaults={
                'report_type': 'balance_sheet',
                'description': 'Test template for debugging parent account calculations',
                'is_active': True,
                'is_default': False,
            }
        )
        
        if not created:
            self.stdout.write(self.style.WARNING('Template already exists. Deleting old line templates...'))
            template.line_templates.all().delete()
        
        # Create line templates
        line_number = 1
        
        # Header
        FinancialStatementLineTemplate.objects.create(
            template=template,
            line_number=line_number,
            label='PARENT ACCOUNT TEST',
            line_type='header',
            calculation_type='sum',
            indent_level=0,
            is_bold=True,
        )
        line_number += 1
        
        # Spacer
        FinancialStatementLineTemplate.objects.create(
            template=template,
            line_number=line_number,
            label='',
            line_type='spacer',
            calculation_type='sum',
            indent_level=0,
        )
        line_number += 1
        
        # Add lines for each parent account
        for parent_account in parent_accounts:
            # Parent account line
            FinancialStatementLineTemplate.objects.create(
                template=template,
                line_number=line_number,
                label=f'{parent_account.account_code} - {parent_account.name} (PARENT)',
                line_type='account',
                account=parent_account,
                calculation_type='balance',
                indent_level=0,
                is_bold=True,
            )
            line_number += 1
            
            # Children accounts
            children = parent_account.get_children().filter(company_id=company_id)
            for child in children:
                FinancialStatementLineTemplate.objects.create(
                    template=template,
                    line_number=line_number,
                    label=f'  {child.account_code} - {child.name}',
                    line_type='account',
                    account=child,
                    calculation_type='balance',
                    indent_level=1,
                    is_bold=False,
                )
                line_number += 1
            
            # Spacer after each parent group
            FinancialStatementLineTemplate.objects.create(
                template=template,
                line_number=line_number,
                label='',
                line_type='spacer',
                calculation_type='sum',
                indent_level=0,
            )
            line_number += 1
        
        # Total line
        FinancialStatementLineTemplate.objects.create(
            template=template,
            line_number=line_number,
            label='TOTAL',
            line_type='total',
            calculation_type='formula',
            formula='L2',  # Will be calculated from all parent lines
            indent_level=0,
            is_bold=True,
        )
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Created test template: "{template.name}" (ID: {template.id})\n'
            f'  - Report Type: {template.get_report_type_display()}\n'
            f'  - Lines Created: {template.line_templates.count()}\n'
            f'  - Parent Accounts Tested: {len(parent_accounts)}\n'
        ))
        self.stdout.write(
            f'\nTo preview this template, run:\n'
            f'  python manage.py test_financial_statements --company-id {company_id} '
            f'--template-id {template.id} --preview --debug-accounts\n'
        )
    
    def generate_preview(
        self,
        company_id,
        template_id,
        start_date,
        end_date,
        as_of_date,
        include_pending,
        debug_accounts
    ):
        """Generate a preview of the financial statement with debugging info."""
        try:
            template = FinancialStatementTemplate.objects.get(
                id=template_id,
                company_id=company_id
            )
        except FinancialStatementTemplate.DoesNotExist:
            raise CommandError(f'Template {template_id} not found for company {company_id}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n{"="*80}\n'
            f'FINANCIAL STATEMENT PREVIEW\n'
            f'{"="*80}\n'
        ))
        self.stdout.write(f'Template: {template.name} (ID: {template.id})')
        self.stdout.write(f'Report Type: {template.get_report_type_display()}')
        self.stdout.write(f'Period: {start_date} to {end_date}')
        self.stdout.write(f'As of Date: {as_of_date}')
        self.stdout.write(f'Include Pending: {include_pending}')
        self.stdout.write(f'\n{"="*80}\n')
        
        # Generate preview
        generator = FinancialStatementGenerator(company_id=company_id)
        preview_data = generator.preview_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            include_pending=include_pending,
        )
        
        # Display lines
        self.stdout.write(f'\n{"Line":<6} {"Label":<50} {"Balance":>20}')
        self.stdout.write('-' * 80)
        
        for line_data in preview_data.get('lines', []):
            line_num = line_data.get('line_number', 0)
            label = line_data.get('label', '')
            balance = line_data.get('balance', 0.0)
            
            # Format balance
            balance_str = f'{balance:,.2f}'
            if balance == 0:
                balance_str = self.style.WARNING(balance_str)
            elif balance < 0:
                balance_str = self.style.ERROR(balance_str)
            
            # Bold formatting
            if line_data.get('is_bold', False):
                label = self.style.BOLD(label)
                balance_str = self.style.BOLD(balance_str)
            
            self.stdout.write(f'{line_num:<6} {label:<50} {balance_str:>20}')
        
        # Display totals
        if preview_data.get('total_assets') is not None:
            self.stdout.write(f'\nTotal Assets: {preview_data["total_assets"]:,.2f}')
        if preview_data.get('total_liabilities') is not None:
            self.stdout.write(f'Total Liabilities: {preview_data["total_liabilities"]:,.2f}')
        if preview_data.get('total_equity') is not None:
            self.stdout.write(f'Total Equity: {preview_data["total_equity"]:,.2f}')
        if preview_data.get('net_income') is not None:
            self.stdout.write(f'Net Income: {preview_data["net_income"]:,.2f}')
        
        # Debug account calculations
        if debug_accounts:
            self.debug_account_calculations(
                company_id,
                template,
                start_date,
                end_date,
                as_of_date,
                include_pending
            )
        
        # Save preview to file
        output_file = f'financial_statement_preview_{template_id}_{date.today()}.json'
        with open(output_file, 'w') as f:
            json.dump(preview_data, f, indent=2, default=str)
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ Preview saved to: {output_file}'))
    
    def debug_account_calculations(
        self,
        company_id,
        template,
        start_date,
        end_date,
        as_of_date,
        include_pending
    ):
        """Show detailed debugging information for account calculations."""
        self.stdout.write(self.style.SUCCESS(f'\n{"="*80}\n'))
        self.stdout.write(self.style.SUCCESS('DETAILED ACCOUNT CALCULATION DEBUGGING'))
        self.stdout.write(self.style.SUCCESS(f'{"="*80}\n'))
        
        generator = FinancialStatementGenerator(company_id=company_id)
        
        for line_template in template.line_templates.all().order_by('line_number'):
            if line_template.line_type in ('header', 'spacer'):
                continue
            
            if not line_template.account:
                continue
            
            account = line_template.account
            self.stdout.write(f'\n{"-"*80}')
            self.stdout.write(f'Line {line_template.line_number}: {line_template.label}')
            self.stdout.write(f'Account: {account.account_code} - {account.name} (ID: {account.id})')
            self.stdout.write(f'Is Leaf: {account.is_leaf()}')
            self.stdout.write(f'Account Direction: {account.account_direction}')
            self.stdout.write(f'Stored Balance: {account.balance}')
            self.stdout.write(f'Balance Date: {account.balance_date}')
            
            if account.is_leaf():
                # Leaf account - show journal entries
                state_filter = Q(state='posted')
                if include_pending:
                    state_filter = Q(state__in=['posted', 'pending'])
                
                entries = JournalEntry.objects.filter(
                    account=account,
                    transaction__company_id=company_id,
                ).filter(state_filter)
                
                if start_date:
                    entries = entries.filter(
                        Q(date__gte=start_date) | (Q(date__isnull=True) & Q(transaction__date__gte=start_date))
                    )
                if end_date:
                    entries = entries.filter(
                        Q(date__lte=end_date) | (Q(date__isnull=True) & Q(transaction__date__lte=end_date))
                    )
                
                totals = entries.aggregate(
                    total_debit=Sum('debit_amount'),
                    total_credit=Sum('credit_amount')
                )
                
                total_debit = totals['total_debit'] or Decimal('0.00')
                total_credit = totals['total_credit'] or Decimal('0.00')
                net_movement = total_debit - total_credit
                balance = net_movement * account.account_direction
                
                self.stdout.write(f'  Entry Count: {entries.count()}')
                self.stdout.write(f'  Total Debit: {total_debit:,.2f}')
                self.stdout.write(f'  Total Credit: {total_credit:,.2f}')
                self.stdout.write(f'  Net Movement: {net_movement:,.2f}')
                self.stdout.write(f'  Calculated Balance: {balance:,.2f}')
                
            else:
                # Parent account - show children
                all_children = account.get_children()
                children = all_children.filter(company_id=company_id)
                self.stdout.write(f'  Total Children (all companies): {all_children.count()}')
                self.stdout.write(f'  Children (company {company_id}): {children.count()}')
                
                if all_children.exists() and not children.exists():
                    self.stdout.write(self.style.ERROR(
                        f'  ⚠ WARNING: Parent has {all_children.count()} children, but NONE belong to company {company_id}!'
                    ))
                    self.stdout.write('  Children with different company_id:')
                    for child in all_children[:5]:  # Show first 5
                        self.stdout.write(f'    - {child.account_code} - {child.name} (Company ID: {child.company_id})')
                
                if not children.exists():
                    self.stdout.write(self.style.ERROR('  ⚠ WARNING: Parent account has no children for this company!'))
                else:
                    total_children_balance = Decimal('0.00')
                    self.stdout.write('  Children:')
                    
                    for child in children:
                        child_balance = generator._calculate_account_balance_with_children(
                            account=child,
                            include_pending=include_pending,
                            beginning_date=start_date if template.report_type == 'income_statement' else None,
                            end_date=end_date,
                        )
                        total_children_balance += child_balance
                        
                        self.stdout.write(
                            f'    - {child.account_code} - {child.name} (ID: {child.id}): '
                            f'{child_balance:,.2f}'
                        )
                    
                    self.stdout.write(f'  Sum of Children: {total_children_balance:,.2f}')
                    
                    # Calculate what the parent should be
                    parent_balance = generator._calculate_account_balance_with_children(
                        account=account,
                        include_pending=include_pending,
                        beginning_date=start_date if template.report_type == 'income_statement' else None,
                        end_date=end_date,
                    )
                    self.stdout.write(f'  Parent Calculated Balance: {parent_balance:,.2f}')
                    
                    if abs(total_children_balance - parent_balance) > Decimal('0.01'):
                        self.stdout.write(self.style.ERROR(
                            f'  ⚠ WARNING: Mismatch! Sum of children ({total_children_balance:,.2f}) '
                            f'≠ Parent balance ({parent_balance:,.2f})'
                        ))
                    else:
                        self.stdout.write(self.style.SUCCESS('  ✓ Balance matches sum of children'))

