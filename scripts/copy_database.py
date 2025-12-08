#!/usr/bin/env python
"""
Fast database copy script using direct SQL COPY.
Copies data from production to homologation database.
"""
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nord_backend.settings')

import django
django.setup()

from django.db import connections
from django.apps import apps


def get_table_order():
    """Get tables in order respecting foreign key dependencies."""
    # Core tables first, then dependent tables
    priority_tables = [
        'auth_group',
        'multitenancy_company',
        'multitenancy_customuser',
        'multitenancy_customuser_groups',
        'multitenancy_customuser_user_permissions',
        'accounting_currency',
        'accounting_account',
        'accounting_entity',
        'accounting_bankaccount',
    ]
    return priority_tables


def copy_table(source_cursor, target_cursor, table_name, batch_size=1000):
    """Copy a single table from source to target."""
    try:
        # Get column names
        source_cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, [table_name])
        columns = [row[0] for row in source_cursor.fetchall()]
        
        if not columns:
            print(f"  Skipping {table_name}: no columns found")
            return 0
        
        # Count source records
        source_cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        total = source_cursor.fetchone()[0]
        
        if total == 0:
            print(f"  {table_name}: 0 records")
            return 0
        
        print(f"  Copying {table_name}: {total} records...", end="", flush=True)
        
        # Clear target table
        target_cursor.execute(f'TRUNCATE TABLE "{table_name}" CASCADE')
        
        # Copy in batches
        cols_str = ', '.join([f'"{c}"' for c in columns])
        placeholders = ', '.join(['%s'] * len(columns))
        
        offset = 0
        copied = 0
        
        while offset < total:
            source_cursor.execute(f'''
                SELECT {cols_str} FROM "{table_name}" 
                ORDER BY 1 
                LIMIT {batch_size} OFFSET {offset}
            ''')
            rows = source_cursor.fetchall()
            
            if not rows:
                break
            
            for row in rows:
                try:
                    target_cursor.execute(
                        f'INSERT INTO "{table_name}" ({cols_str}) VALUES ({placeholders})',
                        row
                    )
                    copied += 1
                except Exception as e:
                    # Skip duplicates or constraint violations
                    pass
            
            offset += batch_size
            print(".", end="", flush=True)
        
        print(f" {copied} copied")
        return copied
        
    except Exception as e:
        print(f" ERROR: {e}")
        return 0


def main():
    print("\n" + "=" * 60)
    print("DATABASE COPY: Production -> Homologation")
    print("=" * 60)
    
    # Get connections
    source_conn = connections['production']
    target_conn = connections['default']
    
    print(f"\nSource: {source_conn.settings_dict['HOST']}")
    print(f"Target: {target_conn.settings_dict['HOST']}")
    
    # Get all tables
    with source_conn.cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        all_tables = [row[0] for row in cursor.fetchall()]
    
    print(f"\nFound {len(all_tables)} tables to copy")
    
    # Skip Django system tables
    skip_tables = {
        'django_migrations',
        'django_content_type', 
        'django_admin_log',
        'django_session',
        'auth_permission',
    }
    
    tables_to_copy = [t for t in all_tables if t not in skip_tables]
    
    print(f"Copying {len(tables_to_copy)} tables (skipping system tables)")
    print("-" * 60)
    
    total_copied = 0
    with source_conn.cursor() as source_cursor:
        with target_conn.cursor() as target_cursor:
            for table in tables_to_copy:
                copied = copy_table(source_cursor, target_cursor, table)
                total_copied += copied
    
    print("-" * 60)
    print(f"COMPLETE: Copied {total_copied} total records")
    print("=" * 60)


if __name__ == '__main__':
    main()


