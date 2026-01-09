"""
Management command to diagnose why a financial statement line is returning zero.

Usage:
    python manage.py diagnose_financial_statement_line <line_template_id> [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD] [--company-id ID]
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import date, timedelta
import json

from accounting.models_financial_statements import FinancialStatementLineTemplate
from accounting.services.financial_statement_service import FinancialStatementGenerator


class Command(BaseCommand):
    help = 'Diagnose why a financial statement line is returning zero'

    def add_arguments(self, parser):
        parser.add_argument(
            'line_template_id',
            type=int,
            help='ID of the FinancialStatementLineTemplate to diagnose'
        )
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date (YYYY-MM-DD). Defaults to 2025-01-01.',
        )
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date (YYYY-MM-DD). Defaults to 2025-12-31.',
        )
        parser.add_argument(
            '--company-id',
            type=int,
            help='Company ID. Required if not set in template.',
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['json', 'pretty'],
            default='pretty',
            help='Output format (json or pretty)',
        )

    def handle(self, *args, **options):
        line_template_id = options['line_template_id']
        
        try:
            line_template = FinancialStatementLineTemplate.objects.get(id=line_template_id)
        except FinancialStatementLineTemplate.DoesNotExist:
            raise CommandError(f'FinancialStatementLineTemplate with ID {line_template_id} does not exist')
        
        # Get company ID
        company_id = options.get('company_id')
        if not company_id:
            if line_template.template and line_template.template.company_id:
                company_id = line_template.template.company_id
            else:
                raise CommandError('Company ID is required. Use --company-id or ensure template has company_id')
        
        # Parse dates
        if options['end_date']:
            end_date = date.fromisoformat(options['end_date'])
        else:
            # Default to end of 2025 (since 2026 doesn't have records yet)
            end_date = date(2025, 12, 31)
        
        if options['start_date']:
            start_date = date.fromisoformat(options['start_date'])
        else:
            # Default to start of 2025
            start_date = date(2025, 1, 1)
        
        self.stdout.write(self.style.SUCCESS(
            f'\nDiagnosing Line Template ID {line_template_id}: "{line_template.label}"\n'
            f'Template: {line_template.template.name if line_template.template else "None"}\n'
            f'Period: {start_date} to {end_date}\n'
            f'Company ID: {company_id}\n'
            f'{"="*80}\n'
        ))
        
        # Run diagnosis
        generator = FinancialStatementGenerator(company_id=company_id)
        diagnosis = generator.diagnose_line_calculation(
            line_template=line_template,
            start_date=start_date,
            end_date=end_date,
        )
        
        # Output results
        if options['format'] == 'json':
            self.stdout.write(json.dumps(diagnosis, indent=2, default=str))
        else:
            self._output_pretty(diagnosis)
    
    def _output_pretty(self, diagnosis):
        """Output diagnosis in a human-readable format."""
        # Line Template Info
        self.stdout.write(self.style.SUCCESS('\n📋 LINE TEMPLATE INFO'))
        self.stdout.write(f"  Line Number: {diagnosis['line_template']['line_number']}")
        self.stdout.write(f"  Label: {diagnosis['line_template']['label']}")
        self.stdout.write(f"  Calculation Method: {diagnosis['line_template']['calculation_method']}")
        self.stdout.write(f"  Account ID: {diagnosis['line_template']['account_id']}")
        self.stdout.write(f"  Account Path Contains: {diagnosis['line_template']['account_path_contains']}")
        self.stdout.write(f"  Include Descendants: {diagnosis['line_template']['include_descendants']}")
        
        # Date Range
        self.stdout.write(self.style.SUCCESS('\n📅 DATE RANGE'))
        self.stdout.write(f"  Start Date: {diagnosis['date_range']['start_date']}")
        self.stdout.write(f"  End Date: {diagnosis['date_range']['end_date']}")
        self.stdout.write(f"  As Of Date: {diagnosis['date_range']['as_of_date']}")
        
        # Accounts Selected
        self.stdout.write(self.style.SUCCESS(f'\n🏦 ACCOUNTS SELECTED ({len(diagnosis["accounts_selected"])})'))
        if not diagnosis['accounts_selected']:
            self.stdout.write(self.style.ERROR('  ⚠️  NO ACCOUNTS FOUND!'))
        else:
            for acc in diagnosis['accounts_selected']:
                self.stdout.write(
                    f"  • {acc['code']} - {acc['name']} "
                    f"(ID: {acc['id']}, Leaf: {acc['is_leaf']}, Direction: {acc['account_direction']})"
                )
        
        # Journal Entries
        self.stdout.write(self.style.SUCCESS(f'\n📝 JOURNAL ENTRIES'))
        for acc_info in diagnosis['journal_entries']:
            self.stdout.write(
                f"\n  Account: {acc_info['account_code']} - {acc_info['account_name']} (ID: {acc_info['account_id']})"
            )
            self.stdout.write(f"    Total entries (all time): {acc_info['total_entries_all_time']}")
            self.stdout.write(f"    Entries in date range: {acc_info['entries_in_date_range']}")
            self.stdout.write(f"    Posted entries in range: {acc_info['posted_entries_in_range']}")
            self.stdout.write(f"    Pending entries in range: {acc_info['pending_entries_in_range']}")
            
            if acc_info['sample_entries']:
                self.stdout.write(f"    Sample entries:")
                for entry in acc_info['sample_entries']:
                    self.stdout.write(
                        f"      • Date: {entry['date']}, State: {entry['state']}, "
                        f"Debit: {entry['debit_amount']}, Credit: {entry['credit_amount']}"
                    )
        
        # Calculation Result
        self.stdout.write(self.style.SUCCESS(f'\n💰 CALCULATION RESULT'))
        result = diagnosis['calculation_result']
        if isinstance(result, (int, float)):
            if result == 0:
                self.stdout.write(self.style.WARNING(f"  Result: {result} (ZERO)"))
            else:
                self.stdout.write(self.style.SUCCESS(f"  Result: {result}"))
        else:
            self.stdout.write(f"  Result: {result}")
        
        # Additional checks
        self.stdout.write(self.style.SUCCESS('\n🔍 ADDITIONAL CHECKS'))
        
        # Check parent account
        line_template_obj = FinancialStatementLineTemplate.objects.get(id=diagnosis['line_template']['id'])
        if line_template_obj.account and not line_template_obj.account.is_leaf():
            from accounting.models import JournalEntry
            parent = line_template_obj.account
            parent_entries_all = JournalEntry.objects.filter(
                account=parent,
                transaction__company_id=company_id,
            )
            parent_entries_range = parent_entries_all.filter(
                date__gte=start_date,
                date__lte=end_date,
            )
            
            if parent_entries_all.count() > 0:
                self.stdout.write(self.style.WARNING(
                    f"\n  ⚠️  PARENT ACCOUNT '{parent.name}' (ID: {parent.id}) has entries!"
                ))
                self.stdout.write(f"    Total entries: {parent_entries_all.count()}")
                self.stdout.write(f"    Entries in range [{start_date}, {end_date}]: {parent_entries_range.count()}")
                self.stdout.write(
                    self.style.ERROR(
                        "    ⚠️  Entries may be linked to parent account instead of leaf accounts!"
                    )
                )
                diagnosis['issues'].append(
                    f"Parent account {parent.name} (ID: {parent.id}) has {parent_entries_all.count()} entries. "
                    "Entries should be linked to leaf accounts, not the parent."
                )
            else:
                self.stdout.write(f"  ✓ Parent account '{parent.name}' has no entries")
        
        # Check for entries in any account matching the path
        if line_template_obj.account_path_contains:
            from accounting.models import Account
            all_accounts = Account.objects.filter(company_id=company_id)
            matching_accounts = []
            for acc in all_accounts:
                try:
                    path = acc.get_path()
                    if line_template_obj.account_path_contains.lower() in path.lower():
                        matching_accounts.append(acc)
                except:
                    pass
            
            if matching_accounts:
                accounts_with_entries = []
                for acc in matching_accounts:
                    entry_count = JournalEntry.objects.filter(
                        account=acc,
                        transaction__company_id=company_id,
                    ).count()
                    if entry_count > 0:
                        accounts_with_entries.append((acc, entry_count))
                
                if accounts_with_entries:
                    self.stdout.write(self.style.WARNING(
                        f"\n  ⚠️  Found accounts matching path '{line_template_obj.account_path_contains}' with entries:"
                    ))
                    for acc, count in accounts_with_entries:
                        self.stdout.write(f"    • {acc.name} (ID: {acc.id}): {count} entries")
                    diagnosis['issues'].append(
                        f"Found {len(accounts_with_entries)} account(s) matching path filter with entries "
                        "that weren't selected. Check account selection logic."
                    )
        
        # Issues
        if diagnosis['issues']:
            self.stdout.write(self.style.ERROR(f'\n⚠️  ISSUES FOUND ({len(diagnosis["issues"])})'))
            for issue in diagnosis['issues']:
                self.stdout.write(f"  • {issue}")
        else:
            self.stdout.write(self.style.SUCCESS('\n✅ No obvious issues found'))
        
        self.stdout.write('\n')

