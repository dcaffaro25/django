"""
Script to delete and recreate the AccountBalanceHistory table.

Usage:
    python manage.py shell < scripts/recreate_balance_history_table.py
    
Or run interactively:
    python manage.py shell
    >>> exec(open('scripts/recreate_balance_history_table.py').read())
"""

from django.db import connection

# Drop the table if it exists
with connection.cursor() as cursor:
    print("Dropping AccountBalanceHistory table if it exists...")
    cursor.execute("DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;")
    print("Table dropped successfully.")

print("\nNow run:")
print("  python manage.py migrate accounting 0062 --fake")
print("  python manage.py migrate accounting 0062")
print("\nOr simply:")
print("  python manage.py migrate accounting")

