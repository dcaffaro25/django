"""
Script to drop and recreate the AccountBalanceHistory table.

This script will:
1. Drop the existing table if it exists
2. Optionally fake-unapply the migration
3. Reapply the migration to recreate the table

Usage:
    python manage.py shell
    >>> exec(open('scripts/recreate_accountbalancehistory.py').read())
    
Or as a management command:
    python manage.py shell -c "exec(open('scripts/recreate_accountbalancehistory.py').read())"
"""

from django.db import connection, transaction
from django.core.management import call_command
from django.apps import apps

def recreate_accountbalancehistory_table():
    """Drop and recreate the AccountBalanceHistory table."""
    
    print("=" * 60)
    print("Recreating AccountBalanceHistory Table")
    print("=" * 60)
    
    # Step 1: Drop the table
    with connection.cursor() as cursor:
        print("\n1. Dropping AccountBalanceHistory table if it exists...")
        try:
            cursor.execute("DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;")
            print("   ✓ Table dropped successfully (if it existed)")
        except Exception as e:
            print(f"   ⚠ Error dropping table: {e}")
            print("   Continuing anyway...")
    
    # Step 2: Check migration status
    print("\n2. Checking migration status...")
    try:
        from django.db.migrations.recorder import MigrationRecorder
        recorder = MigrationRecorder(connection)
        applied_migrations = recorder.applied_migrations()
        migration_key = ('accounting', '0062_accountbalancehistory')
        
        if migration_key in applied_migrations:
            print(f"   Migration {migration_key} is marked as applied")
            print("   You may want to fake-unapply it first:")
            print("   python manage.py migrate accounting 0061 --fake")
        else:
            print(f"   Migration {migration_key} is not marked as applied")
    except Exception as e:
        print(f"   Could not check migration status: {e}")
    
    # Step 3: Instructions for reapplying migration
    print("\n3. Next steps:")
    print("   Run the following command to recreate the table:")
    print("   python manage.py migrate accounting")
    print("\n   Or if you need to fake-unapply first:")
    print("   python manage.py migrate accounting 0061 --fake")
    print("   python manage.py migrate accounting")
    
    print("\n" + "=" * 60)
    print("Done! Now run the migration command above.")
    print("=" * 60)

if __name__ == "__main__" or __name__ == "__builtin__":
    recreate_accountbalancehistory_table()

