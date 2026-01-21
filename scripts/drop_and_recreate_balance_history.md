# How to Delete and Recreate AccountBalanceHistory Table

## Option 1: Using SQL Directly (Quickest)

Run these SQL commands in your database:

```sql
-- Drop the table (this will also drop any dependent objects like indexes)
DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;

-- Then run the migration to recreate it
-- python manage.py migrate accounting
```

## Option 2: Using Django Migrations (Recommended for Production)

### Step 1: Fake unapply the migration (if it's been applied)
```bash
python manage.py migrate accounting 0061 --fake
```

### Step 2: Drop the table manually
```sql
DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;
```

### Step 3: Reapply the migration
```bash
python manage.py migrate accounting
```

## Option 3: Create a New Migration to Drop and Recreate

This is the cleanest approach if you want it tracked in migrations.

Create a new migration file that:
1. Drops the existing table
2. Recreates it with the same structure

This ensures the migration history stays clean.

