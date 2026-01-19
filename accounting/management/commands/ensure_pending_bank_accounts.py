# accounting/management/commands/ensure_pending_bank_accounts.py
"""
Management command to ensure all companies have pending bank accounts.

Usage:
    python manage.py ensure_pending_bank_accounts
    python manage.py ensure_pending_bank_accounts --company-id 5
    python manage.py ensure_pending_bank_accounts --all
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from multitenancy.models import Company
from accounting.services.bank_structs import ensure_pending_bank_structs
from accounting.models import BankAccount, Currency


class Command(BaseCommand):
    help = 'Ensure all companies have pending bank accounts and GL accounts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            help='Ensure pending bank account for a specific company ID',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Ensure pending bank accounts for all companies',
        )
        parser.add_argument(
            '--currency-id',
            type=int,
            help='Currency ID to use (defaults to first available currency)',
        )

    def handle(self, *args, **options):
        company_id = options.get('company_id')
        all_companies = options.get('all', False)
        currency_id = options.get('currency_id')

        if company_id:
            # Ensure for specific company
            companies = Company.objects.filter(id=company_id)
            if not companies.exists():
                self.stdout.write(
                    self.style.ERROR(f'Company with ID {company_id} not found')
                )
                return
        elif all_companies:
            # Ensure for all companies
            companies = Company.objects.all()
            self.stdout.write(f'Processing {companies.count()} companies...')
        else:
            self.stdout.write(
                self.style.ERROR(
                    'Please specify --company-id <id> or --all to process companies'
                )
            )
            return

        # Get currency if specified
        if currency_id:
            currency = Currency.objects.filter(id=currency_id).first()
            if not currency:
                self.stdout.write(
                    self.style.ERROR(f'Currency with ID {currency_id} not found')
                )
                return
            currency_id = currency.id

        success_count = 0
        error_count = 0
        skipped_count = 0

        for company in companies:
            try:
                # Check if pending bank account already exists
                existing = BankAccount.objects.filter(
                    company_id=company.id,
                    name='Pending BankAccount',
                    account_number='PENDING',
                    branch_id='PENDING',
                ).first()

                if existing:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Company {company.id} ({company.name}): Pending bank account already exists (ID: {existing.id})'
                        )
                    )
                    skipped_count += 1
                    continue

                # Ensure pending bank structs
                self.stdout.write(
                    f'Creating pending bank account for company {company.id} ({company.name})...'
                )
                
                # Use a separate transaction for each company to avoid issues
                with transaction.atomic():
                    pending_ba, pending_gl = ensure_pending_bank_structs(
                        company_id=company.id,
                        currency_id=currency_id
                    )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Company {company.id} ({company.name}): '
                        f'Created pending bank account (ID: {pending_ba.id}) and GL account (ID: {pending_gl.id})'
                    )
                )
                success_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'✗ Company {company.id} ({company.name}): Error - {str(e)}'
                    )
                )
                error_count += 1

        # Summary
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'Summary:'))
        self.stdout.write(f'  Successfully created: {success_count}')
        self.stdout.write(f'  Already existed (skipped): {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write('=' * 60)

