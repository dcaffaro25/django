# Generated manually to refactor AccountBalanceHistory from multiple records to columns

from django.db import migrations, models
from decimal import Decimal


def migrate_old_to_new_structure(apps, schema_editor):
    """
    Migrate from old structure (multiple records per account/month with balance_type)
    to new structure (single record with columns for each balance type).
    
    This handles the case where the table was created with the old structure.
    """
    AccountBalanceHistory = apps.get_model('accounting', 'AccountBalanceHistory')
    db_alias = schema_editor.connection.alias
    
    # Check if table exists and has old structure
    from django.db import connection
    with connection.cursor() as cursor:
        # Check if balance_type column exists (old structure)
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='accounting_accountbalancehistory' 
            AND column_name='balance_type'
        """)
        has_balance_type = cursor.fetchone() is not None
        
        # Check if posted_opening_balance exists (new structure)
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='accounting_accountbalancehistory' 
            AND column_name='posted_opening_balance'
        """)
        has_new_structure = cursor.fetchone() is not None
    
    if not has_balance_type or has_new_structure:
        # Table doesn't exist, has new structure, or migration not needed
        return
    
    # Get all unique account/month/currency combinations
    from django.db.models import Q
    from collections import defaultdict
    
    # Group by account, year, month, currency
    grouped = defaultdict(dict)
    
    for record in AccountBalanceHistory.objects.using(db_alias).all():
        key = (record.account_id, record.year, record.month, record.currency_id)
        grouped[key][record.balance_type] = record
    
    # Create new records with all balance types in one record
    new_records = []
    for (account_id, year, month, currency_id), balance_types in grouped.items():
        posted = balance_types.get('posted')
        bank_reconciled = balance_types.get('bank_reconciled')
        all_trans = balance_types.get('all')
        
        # Use the first record as base (they all have same account/year/month/currency)
        base = list(balance_types.values())[0]
        
        new_record = AccountBalanceHistory(
            id=base.id,
            company_id=base.company_id,
            account_id=account_id,
            year=year,
            month=month,
            currency_id=currency_id,
            # Posted balances
            posted_opening_balance=posted.opening_balance if posted else Decimal('0.00'),
            posted_ending_balance=posted.ending_balance if posted else Decimal('0.00'),
            posted_total_debit=posted.total_debit if posted else Decimal('0.00'),
            posted_total_credit=posted.total_credit if posted else Decimal('0.00'),
            # Bank-reconciled balances
            bank_reconciled_opening_balance=bank_reconciled.opening_balance if bank_reconciled else Decimal('0.00'),
            bank_reconciled_ending_balance=bank_reconciled.ending_balance if bank_reconciled else Decimal('0.00'),
            bank_reconciled_total_debit=bank_reconciled.total_debit if bank_reconciled else Decimal('0.00'),
            bank_reconciled_total_credit=bank_reconciled.total_credit if bank_reconciled else Decimal('0.00'),
            # All transactions balances
            all_opening_balance=all_trans.opening_balance if all_trans else Decimal('0.00'),
            all_ending_balance=all_trans.ending_balance if all_trans else Decimal('0.00'),
            all_total_debit=all_trans.total_debit if all_trans else Decimal('0.00'),
            all_total_credit=all_trans.total_credit if all_trans else Decimal('0.00'),
            # Metadata
            calculated_at=base.calculated_at,
            calculated_by_id=base.calculated_by_id,
            is_validated=base.is_validated,
            validated_at=base.validated_at,
            validated_by_id=base.validated_by_id,
            created_at=base.created_at,
            updated_at=base.updated_at,
            is_deleted=base.is_deleted,
            notes=base.notes,
            created_by_id=base.created_by_id,
            updated_by_id=base.updated_by_id,
        )
        new_records.append(new_record)
    
    # Delete all old records
    AccountBalanceHistory.objects.using(db_alias).all().delete()
    
    # Bulk create new records
    if new_records:
        AccountBalanceHistory.objects.using(db_alias).bulk_create(new_records)


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: split single records back into multiple records with balance_type.
    """
    AccountBalanceHistory = apps.get_model('accounting', 'AccountBalanceHistory')
    db_alias = schema_editor.connection.alias
    
    new_records = []
    for record in AccountBalanceHistory.objects.using(db_alias).all():
        # Create three records, one for each balance type
        for balance_type in ['posted', 'bank_reconciled', 'all']:
            if balance_type == 'posted':
                opening = record.posted_opening_balance
                ending = record.posted_ending_balance
                debit = record.posted_total_debit
                credit = record.posted_total_credit
            elif balance_type == 'bank_reconciled':
                opening = record.bank_reconciled_opening_balance
                ending = record.bank_reconciled_ending_balance
                debit = record.bank_reconciled_total_debit
                credit = record.bank_reconciled_total_credit
            else:  # all
                opening = record.all_opening_balance
                ending = record.all_ending_balance
                debit = record.all_total_debit
                credit = record.all_total_credit
            
            new_record = AccountBalanceHistory(
                company_id=record.company_id,
                account_id=record.account_id,
                year=record.year,
                month=record.month,
                currency_id=record.currency_id,
                balance_type=balance_type,
                opening_balance=opening,
                ending_balance=ending,
                total_debit=debit,
                total_credit=credit,
                calculated_at=record.calculated_at,
                calculated_by_id=record.calculated_by_id,
                is_validated=record.is_validated,
                validated_at=record.validated_at,
                validated_by_id=record.validated_by_id,
                created_at=record.created_at,
                updated_at=record.updated_at,
                is_deleted=record.is_deleted,
                notes=record.notes,
                created_by_id=record.created_by_id,
                updated_by_id=record.updated_by_id,
            )
            new_records.append(new_record)
    
    # Delete all current records
    AccountBalanceHistory.objects.using(db_alias).all().delete()
    
    # Bulk create old structure records
    if new_records:
        AccountBalanceHistory.objects.using(db_alias).bulk_create(new_records)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0063_rename_accounting__company_7bdf24_idx_accounting__company_7304ab_idx'),
    ]

    operations = [
        # First, check if we need to migrate data and alter structure
        migrations.RunPython(migrate_old_to_new_structure, reverse_migration),
        
        # Then alter the table structure
        # Use RunSQL to safely remove/add fields only if they exist/don't exist
        migrations.RunSQL(
            # Remove old fields if they exist
            sql="""
                DO $$ 
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='accounting_accountbalancehistory' 
                              AND column_name='balance_type') THEN
                        ALTER TABLE accounting_accountbalancehistory DROP COLUMN balance_type;
                    END IF;
                    
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='accounting_accountbalancehistory' 
                              AND column_name='opening_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory DROP COLUMN opening_balance;
                    END IF;
                    
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='accounting_accountbalancehistory' 
                              AND column_name='ending_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory DROP COLUMN ending_balance;
                    END IF;
                    
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='accounting_accountbalancehistory' 
                              AND column_name='total_debit') THEN
                        ALTER TABLE accounting_accountbalancehistory DROP COLUMN total_debit;
                    END IF;
                    
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='accounting_accountbalancehistory' 
                              AND column_name='total_credit') THEN
                        ALTER TABLE accounting_accountbalancehistory DROP COLUMN total_credit;
                    END IF;
                END $$;
            """,
            reverse_sql="""
                -- Reverse migration would need to add back balance_type and old fields
                -- This is complex and may not be needed
            """
        ),
        
        # Add new fields using RunSQL to make it idempotent
        migrations.RunSQL(
            sql="""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='posted_opening_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN posted_opening_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='posted_ending_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN posted_ending_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='posted_total_debit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN posted_total_debit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='posted_total_credit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN posted_total_credit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='bank_reconciled_opening_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN bank_reconciled_opening_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='bank_reconciled_ending_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN bank_reconciled_ending_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='bank_reconciled_total_debit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN bank_reconciled_total_debit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='bank_reconciled_total_credit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN bank_reconciled_total_credit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='all_opening_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN all_opening_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='all_ending_balance') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN all_ending_balance NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='all_total_debit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN all_total_debit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name='accounting_accountbalancehistory' 
                                  AND column_name='all_total_credit') THEN
                        ALTER TABLE accounting_accountbalancehistory 
                        ADD COLUMN all_total_credit NUMERIC(18,2) DEFAULT 0.00;
                    END IF;
                END $$;
            """,
            reverse_sql="""
                -- Reverse would drop these columns
            """
        ),
        
        # Note: The model fields are defined in 0062, but we use RunSQL above
        # to make the migration idempotent and handle cases where 0062 wasn't run
        # or was run with old structure. The RunSQL adds the columns if they don't exist.
        
        # Update unique constraint (remove balance_type if it was in the constraint)
        migrations.AlterUniqueTogether(
            name='accountbalancehistory',
            unique_together={('company', 'account', 'year', 'month', 'currency')},
        ),
        
        # Update indexes
        migrations.AlterIndexTogether(
            name='accountbalancehistory',
            index_together=set(),
        ),
    ]

