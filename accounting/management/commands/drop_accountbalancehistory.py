"""
Django management command to drop the AccountBalanceHistory table.

This command can be run on Railway to drop the table before recreating it.

Usage:
    python manage.py drop_accountbalancehistory
    
    # On Railway:
    railway run python manage.py drop_accountbalancehistory
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings


class Command(BaseCommand):
    help = 'Drop the AccountBalanceHistory table if it exists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt (useful for automated scripts)',
        )
        parser.add_argument(
            '--check-migration',
            action='store_true',
            help='Check if migration 0062 is applied before dropping',
        )

    def handle(self, *args, **options):
        confirm = options.get('confirm', False)
        check_migration = options.get('check_migration', False)
        
        self.stdout.write(self.style.WARNING('=' * 60))
        self.stdout.write(self.style.WARNING('Drop AccountBalanceHistory Table'))
        self.stdout.write(self.style.WARNING('=' * 60))
        
        # Check migration status if requested
        if check_migration:
            try:
                from django.db.migrations.recorder import MigrationRecorder
                recorder = MigrationRecorder(connection)
                applied_migrations = recorder.applied_migrations()
                migration_key = ('accounting', '0062_accountbalancehistory')
                
                if migration_key in applied_migrations:
                    self.stdout.write(
                        self.style.WARNING(
                            f'⚠ Migration {migration_key} is marked as applied. '
                            'You may want to fake-unapply it first:'
                        )
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            '  python manage.py migrate accounting 0061 --fake'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Migration {migration_key} is not marked as applied'
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Could not check migration status: {e}')
                )
        
        # Check if table exists
        table_exists = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'accounting_accountbalancehistory'
                    );
                """)
                table_exists = cursor.fetchone()[0]
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error checking if table exists: {e}')
            )
            return
        
        if not table_exists:
            self.stdout.write(
                self.style.WARNING(
                    '⚠ Table accounting_accountbalancehistory does not exist. Nothing to drop.'
                )
            )
            return
        
        # Confirmation prompt
        if not confirm:
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠ WARNING: This will permanently delete the AccountBalanceHistory table '
                    'and all its data!'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    'You can recreate it by running: python manage.py migrate accounting'
                )
            )
            response = input('\nAre you sure you want to proceed? (yes/no): ')
            if response.lower() not in ('yes', 'y'):
                self.stdout.write(self.style.WARNING('Operation cancelled.'))
                return
        
        # Drop the table
        try:
            with connection.cursor() as cursor:
                self.stdout.write('\nDropping table accounting_accountbalancehistory...')
                cursor.execute("DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;")
                self.stdout.write(
                    self.style.SUCCESS('✓ Table dropped successfully!')
                )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Error dropping table: {e}')
            )
            return
        
        # Instructions for recreation
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('Next steps:'))
        self.stdout.write(
            '1. Run migration to recreate the table:'
        )
        self.stdout.write(
            self.style.SUCCESS('   python manage.py migrate accounting')
        )
        self.stdout.write(
            '\n2. If migration 0062 is already marked as applied, you may need to:'
        )
        self.stdout.write(
            self.style.WARNING('   python manage.py migrate accounting 0061 --fake')
        )
        self.stdout.write(
            self.style.WARNING('   python manage.py migrate accounting')
        )
        self.stdout.write('=' * 60)

