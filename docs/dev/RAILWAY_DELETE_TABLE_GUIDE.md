# How to Delete AccountBalanceHistory Table on Railway

## Option 1: Using Railway CLI (Recommended)

### Step 1: Install Railway CLI (if not already installed)
```bash
npm i -g @railway/cli
# or
brew install railway
```

### Step 2: Login to Railway
```bash
railway login
```

### Step 3: Link to your project
```bash
railway link
```

### Step 4: Connect to PostgreSQL and drop the table
```bash
# Connect to the database shell
railway connect postgres

# Then in the PostgreSQL shell, run:
DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;
```

### Step 5: Recreate the table via migration
```bash
# Run migration on Railway
railway run python manage.py migrate accounting
```

---

## Option 2: Using Railway Dashboard (Web Interface)

1. **Go to your Railway project dashboard**
2. **Click on your PostgreSQL service**
3. **Go to the "Data" or "Query" tab**
4. **Run this SQL command:**
   ```sql
   DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;
   ```
5. **After dropping, trigger a deployment or run migrations manually:**
   - Go to your Django service
   - Click "Deploy" or use the console to run:
     ```bash
     python manage.py migrate accounting
     ```

---

## Option 3: Using Railway Shell/Console

### Step 1: Access Railway console
```bash
railway shell
```

### Step 2: Run Django management command to drop and recreate
```bash
# This will use Django's database connection
python manage.py shell
```

Then in Python shell:
```python
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;")
    print("Table dropped successfully!")

# Exit shell, then run migration
exit()
```

### Step 3: Run migration
```bash
python manage.py migrate accounting
```

---

## Option 4: Create a Django Management Command (Best for Repeated Use)

This creates a reusable command you can run on Railway.

### Create the command file:
```bash
# File: accounting/management/commands/drop_accountbalancehistory.py
```

Then run on Railway:
```bash
railway run python manage.py drop_accountbalancehistory
railway run python manage.py migrate accounting
```

---

## Option 5: Using Direct PostgreSQL Connection

If you have the database credentials from Railway environment variables:

```bash
# Get connection string from Railway dashboard or:
railway variables

# Then connect using psql:
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE"

# Or use the full connection string:
psql "postgresql://postgres:password@host.proxy.rlwy.net:port/railway"
```

Then run:
```sql
DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;
\q
```

---

## Quick One-Liner (Railway CLI)

```bash
# Drop table and recreate via migration
railway connect postgres -c "DROP TABLE IF EXISTS accounting_accountbalancehistory CASCADE;" && railway run python manage.py migrate accounting
```

---

## Important Notes

⚠️ **Backup First**: Consider backing up your database before dropping tables:
```bash
railway connect postgres -c "pg_dump railway > backup.sql"
```

⚠️ **After Dropping**: The table will be automatically recreated when you run:
```bash
railway run python manage.py migrate accounting
```

⚠️ **Migration State**: If the migration 0062 is already applied, you may need to:
1. Fake unapply it first: `python manage.py migrate accounting 0061 --fake`
2. Drop the table
3. Reapply: `python manage.py migrate accounting`

---

## Verification

After recreating, verify the table exists:
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_name = 'accounting_accountbalancehistory';
```

