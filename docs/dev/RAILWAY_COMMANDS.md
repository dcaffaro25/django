# Railway Commands for Windows

## Connect to PostgreSQL Service with Spaces in Name

If your service name has spaces (like "PostgreSQL Vector Prod"), you need to quote it:

```bash
railway connect "PostgreSQL Vector Prod"
```

Or use the service ID instead:
```bash
# List services to get the ID
railway service

# Then connect using the service ID
railway connect <service-id>
```

## Alternative: Use Django Management Command (Easier!)

Instead of connecting to PostgreSQL directly, use the management command:

```bash
# Drop the table
railway run python manage.py drop_accountbalancehistory

# Recreate it
railway run python manage.py migrate accounting
```

## Or Use Railway Shell

```bash
# Open Railway shell
railway shell

# Then run Python commands
python manage.py drop_accountbalancehistory
python manage.py migrate accounting
```

