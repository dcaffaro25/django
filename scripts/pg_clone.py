#!/usr/bin/env python
"""
Fast PostgreSQL database clone using COPY command.
Equivalent to pg_dump | psql but using Python.

Usage:
    python scripts/pg_clone.py
"""
import os
import sys
import io
import time

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nord_backend.settings')

import django
django.setup()

import psycopg2
from django.conf import settings


def get_connection(db_config):
    """Create a psycopg2 connection from Django config."""
    host = str(db_config['HOST']).strip('"').strip("'")
    port = str(db_config['PORT']).strip('"').strip("'")
    name = str(db_config['NAME']).strip('"').strip("'")
    user = str(db_config['USER']).strip('"').strip("'")
    password = str(db_config['PASSWORD']).strip('"').strip("'")
    
    print(f"  Connecting to {host}:{port}/{name}...")
    
    return psycopg2.connect(
        host=host,
        port=port,
        database=name,
        user=user,
        password=password,
    )


def get_tables(cursor):
    """Get all tables in dependency order."""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    return [row[0] for row in cursor.fetchall()]


def get_table_columns(cursor, table_name):
    """Get column names for a table."""
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """, [table_name])
    return [row[0] for row in cursor.fetchall()]


def copy_table_fast(source_conn, target_conn, table_name):
    """Copy table using PostgreSQL COPY command (very fast)."""
    try:
        source_cur = source_conn.cursor()
        target_cur = target_conn.cursor()
        
        # Get row count
        source_cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        count = source_cur.fetchone()[0]
        
        if count == 0:
            print(f"  {table_name}: 0 rows")
            return 0
        
        print(f"  {table_name}: {count} rows...", end="", flush=True)
        
        # Disable triggers during copy
        target_cur.execute(f'ALTER TABLE "{table_name}" DISABLE TRIGGER ALL')
        
        # Truncate target
        target_cur.execute(f'TRUNCATE TABLE "{table_name}" CASCADE')
        
        # Use COPY for fast transfer via memory buffer
        buffer = io.StringIO()
        
        # Copy OUT from source
        source_cur.copy_expert(
            f'COPY "{table_name}" TO STDOUT WITH CSV HEADER',
            buffer
        )
        
        buffer.seek(0)
        
        # Copy IN to target
        target_cur.copy_expert(
            f'COPY "{table_name}" FROM STDIN WITH CSV HEADER',
            buffer
        )
        
        # Re-enable triggers
        target_cur.execute(f'ALTER TABLE "{table_name}" ENABLE TRIGGER ALL')
        
        target_conn.commit()
        print(f" OK")
        return count
        
    except Exception as e:
        target_conn.rollback()
        print(f" ERROR: {e}")
        return 0
    finally:
        source_cur.close()
        target_cur.close()


def reset_sequences(target_conn, table_name):
    """Reset sequence for a table after copy."""
    try:
        cur = target_conn.cursor()
        cur.execute(f"""
            SELECT pg_get_serial_sequence('"{table_name}"', column_name)
            FROM information_schema.columns
            WHERE table_name = %s 
            AND column_default LIKE 'nextval%%'
            LIMIT 1
        """, [table_name])
        result = cur.fetchone()
        if result and result[0]:
            seq_name = result[0]
            cur.execute(f"""
                SELECT setval('{seq_name}', COALESCE((SELECT MAX(id) FROM "{table_name}"), 1))
            """)
            target_conn.commit()
    except:
        pass


def main():
    start_time = time.time()
    
    print("\n" + "=" * 70)
    print("  PostgreSQL Database Clone: Production -> Homologation")
    print("=" * 70)
    
    # Get database configs
    prod_config = settings.DATABASES['production']
    homolog_config = settings.DATABASES['default']
    
    print(f"\nSource (Production): {prod_config['HOST']}:{prod_config['PORT']}/{prod_config['NAME']}")
    print(f"Target (Homologation): {homolog_config['HOST']}:{homolog_config['PORT']}/{homolog_config['NAME']}")
    
    # Connect
    print("\nConnecting...")
    source_conn = get_connection(prod_config)
    target_conn = get_connection(homolog_config)
    print("Connected!")
    
    # Get tables
    source_cur = source_conn.cursor()
    tables = get_tables(source_cur)
    source_cur.close()
    
    # Skip system tables
    skip_tables = {
        'django_migrations',
        'django_content_type',
        'django_admin_log', 
        'django_session',
        'auth_permission',
        'django_celery_results_chordcounter',
        'django_celery_results_groupresult',
        'django_celery_results_taskresult',
    }
    
    tables_to_copy = [t for t in tables if t not in skip_tables]
    
    print(f"\nFound {len(tables)} tables, copying {len(tables_to_copy)} (skipping {len(skip_tables)} system tables)")
    print("-" * 70)
    
    # Copy tables
    total_rows = 0
    errors = []
    
    for table in tables_to_copy:
        rows = copy_table_fast(source_conn, target_conn, table)
        if rows > 0:
            total_rows += rows
            reset_sequences(target_conn, table)
    
    # Close connections
    source_conn.close()
    target_conn.close()
    
    elapsed = time.time() - start_time
    
    print("-" * 70)
    print(f"\nCOMPLETE!")
    print(f"  Tables copied: {len(tables_to_copy)}")
    print(f"  Total rows: {total_rows:,}")
    print(f"  Time: {elapsed:.1f} seconds")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()

