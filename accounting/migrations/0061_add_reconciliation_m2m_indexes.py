# Generated manually for performance optimization
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0060_alter_financialstatementlinetemplate_calculation_type'),
    ]

    operations = [
        # Add composite index on reconciliation_journal_entries through table
        # This speeds up queries filtering by journalentry_id or reconciliation_id
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_reconciliation_journal_entries_recon_je
                ON accounting_reconciliation_journal_entries (reconciliation_id, journalentry_id);
                
                CREATE INDEX IF NOT EXISTS idx_reconciliation_journal_entries_je_recon
                ON accounting_reconciliation_journal_entries (journalentry_id, reconciliation_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_reconciliation_journal_entries_recon_je;
                DROP INDEX IF EXISTS idx_reconciliation_journal_entries_je_recon;
            """
        ),
        # Add composite index on reconciliation_bank_transactions through table
        # This speeds up queries filtering by banktransaction_id or reconciliation_id
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS idx_reconciliation_bank_transactions_recon_bt
                ON accounting_reconciliation_bank_transactions (reconciliation_id, banktransaction_id);
                
                CREATE INDEX IF NOT EXISTS idx_reconciliation_bank_transactions_bt_recon
                ON accounting_reconciliation_bank_transactions (banktransaction_id, reconciliation_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS idx_reconciliation_bank_transactions_recon_bt;
                DROP INDEX IF EXISTS idx_reconciliation_bank_transactions_bt_recon;
            """
        ),
    ]

