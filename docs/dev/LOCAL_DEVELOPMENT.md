# Local Development Setup

This guide explains how to set up a local development environment for testing the Nord Backend application with a homologation database that mirrors production.

## Overview

The local development setup allows you to:
- **Test Celery tasks** with real data without affecting production
- **Clone production data** to a homologation database
- **Debug reconciliation tasks** locally
- **Test all features** in isolation

## Quick Start

### 1. Create Local Credentials File

Copy the example credentials file:
```bash
copy local_credentials.example.ini local_credentials.ini
```

Edit `local_credentials.ini` with your actual credentials:

```ini
[production_database]
name = railway
user = postgres
password = YOUR_PROD_PASSWORD
host = your-prod-host.proxy.rlwy.net
port = 12345

[homologation_database]
name = railway_homolog
user = postgres
password = YOUR_HOMOLOG_PASSWORD
host = your-homolog-host.proxy.rlwy.net
port = 12346

[redis]
# OPTIONAL! Leave commented out - Celery tasks run synchronously without Redis
# url = redis://localhost:6379/0

[environment]
mode = local
```

### 2. Run Migrations on Homologation Database

```bash
python manage.py migrate
```

### 4. Clone Production Data (Optional)

Clone production data to your homologation database:

```bash
# Dry run first (see what would be copied)
run_local.bat clone --dry-run

# Actually clone the data
run_local.bat clone

# Clone with reset (truncate existing data first)
run_local.bat clone --reset
```

### 5. Start Django Server

```bash
run_local.bat
```

That's it! **No Celery worker needed** - tasks run synchronously in the Django process.

> **Note**: If you want async task processing (optional), configure Redis in `local_credentials.ini` and run `run_celery_local.bat` in a separate terminal.

## Detailed Configuration

### Environment Modes

The `mode` setting in `local_credentials.ini` determines behavior:

| Mode | Database Used | Celery Mode | Use Case |
|------|---------------|-------------|----------|
| `local` | Homologation | Real (Redis) | Full local testing |
| `homolog` | Homologation | Real (Redis) | Same as local |
| `production` | Production | Eager (sync) | Default/live |

### Database Configuration

#### Production Database (Read-Only Source)
```ini
[production_database]
name = railway
user = postgres
password = YOUR_PASSWORD
host = your-host.proxy.rlwy.net
port = PORT
```

#### Homologation Database (Testing Target)

You can:
1. **Create a new Railway database** for homologation
2. **Use a local PostgreSQL** instance
3. **Use any PostgreSQL** cloud service

```ini
[homologation_database]
name = railway_homolog
user = postgres
password = YOUR_PASSWORD
host = localhost  # or cloud host
port = 5432
```

### Redis Configuration

```ini
[redis]
url = redis://localhost:6379/0
```

Options:
- **Local Docker**: `redis://localhost:6379/0`
- **Railway Redis**: `redis://default:password@host:port`
- **Upstash Redis**: Your Upstash URL

## Management Commands

### Clone Production to Homologation

```bash
# Basic clone
python manage.py clone_to_homolog

# Clone specific apps only
python manage.py clone_to_homolog --apps accounting multitenancy

# Clone specific companies
python manage.py clone_to_homolog --company-ids 1 2 3

# Dry run (preview only)
python manage.py clone_to_homolog --dry-run

# Reset and clone (truncate existing data)
python manage.py clone_to_homolog --reset

# Skip certain models
python manage.py clone_to_homolog --skip-models auth.Permission
```

### Test Celery Connectivity

```bash
# Basic test
python manage.py test_celery

# Test specific task
python manage.py test_celery --task accounting.tasks.recalculate_status_task

# Async test (don't wait for result)
python manage.py test_celery --async
```

### Explore Data

```bash
# Count records
python manage.py explore_data --model Account --count

# Show samples
python manage.py explore_data --model Transaction --sample 10

# Filter by company
python manage.py explore_data --model JournalEntry --company-id 4
```

## Testing Celery Tasks

### Default: Synchronous Mode (No Worker Needed)

By default, without Redis configured, all Celery tasks run **synchronously**:
- `task.delay()` executes immediately
- `task.apply_async()` executes immediately
- No separate worker process needed
- Results are returned directly

### Optional: Async Mode (Requires Redis)

If you want true async task processing:
1. Configure Redis URL in `local_credentials.ini`
2. Start Celery worker: `run_celery_local.bat`

This starts a worker listening to queues: `celery`, `recon_legacy`, `recon_fast`

### Test from Django Shell

```python
from accounting.tasks import recalculate_status_task, match_many_to_many_task

# Test recalculate task
result = recalculate_status_task.delay()
print(result.get(timeout=30))

# Test reconciliation task (requires a ReconciliationTask object)
from accounting.models import ReconciliationTask
task = ReconciliationTask.objects.create(
    tenant_id='your-tenant',
    parameters={'bank_ids': [1, 2, 3]},
    status='queued'
)
result = match_many_to_many_task.delay(task.id, task.parameters, 'your-tenant')
```

### Monitor with Flower (Optional)

```bash
run_celery_local.bat flower
```

Then open http://localhost:5555 in your browser.

## Batch Scripts Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `run_local.bat` | Start Django server | `run_local.bat` |
| `run_local.bat migrate` | Run migrations | `run_local.bat migrate` |
| `run_local.bat shell` | Django shell | `run_local.bat shell` |
| `run_local.bat clone` | Clone production | `run_local.bat clone` |
| `run_local.bat test` | Run tests | `run_local.bat test` |
| `run_celery_local.bat` | Start Celery worker | `run_celery_local.bat` |
| `run_celery_local.bat beat` | Start Celery Beat | `run_celery_local.bat beat` |
| `run_celery_local.bat flower` | Start Flower UI | `run_celery_local.bat flower` |

## Troubleshooting

### "local_credentials.ini not found"

Copy the example file and fill in credentials:
```bash
copy local_credentials.example.ini local_credentials.ini
```

### "Cannot connect to Redis"

1. Check if Redis is running:
   ```bash
   docker ps | findstr redis
   ```

2. Start Redis if not running:
   ```bash
   docker start redis
   # or
   docker run -d -p 6379:6379 --name redis redis:alpine
   ```

3. Test Redis connection:
   ```bash
   redis-cli ping
   ```

### "CELERY_TASK_ALWAYS_EAGER is True"

This means Celery is running in synchronous mode. Check:
1. Redis is running
2. `[redis] url` is configured in `local_credentials.ini`
3. `[environment] mode` is set to `local` or `homolog`

### "Cannot connect to homologation database"

1. Verify credentials in `local_credentials.ini`
2. Check firewall/network access
3. For Railway: ensure the service is running and port is public

### Tasks hang forever

1. Ensure Celery worker is running: `run_celery_local.bat`
2. Check worker logs for errors
3. Verify Redis connectivity

## Security Notes

⚠️ **IMPORTANT**: The `local_credentials.ini` file contains sensitive credentials and is excluded from git via `.gitignore`. Never commit this file!

The system includes safety checks:
- Clone command requires confirmation
- Clone command validates you're not in production mode
- Production database is never written to

## Architecture

### Default: Synchronous Mode (Simpler)

```
┌─────────────────┐     ┌─────────────────┐
│   Production    │     │  Homologation   │
│    Database     │────▶│    Database     │
│   (read-only)   │     │   (your copy)   │
└─────────────────┘     └─────────────────┘
                               │
                               ▼
        ┌─────────────────────────────────────────┐
        │          Django Application             │
        │   (configured via local_credentials.ini)│
        │                                         │
        │   Celery tasks run SYNCHRONOUSLY        │
        │   (no Redis, no worker needed)          │
        └─────────────────────────────────────────┘
```

### Optional: Async Mode (With Redis)

```
┌─────────────────┐     ┌─────────────────┐
│   Production    │     │  Homologation   │
│    Database     │────▶│    Database     │
│   (read-only)   │     │   (your copy)   │
└─────────────────┘     └─────────────────┘
        │                        │
        ▼                        ▼
┌─────────────────────────────────────────┐
│          Django Application             │
└─────────────────────────────────────────┘
                    │
                    │ tasks
                    ▼
┌─────────────────────────────────────────┐
│            Redis (optional)             │
└─────────────────────────────────────────┘
                    │
                    │ queues
                    ▼
┌─────────────────────────────────────────┐
│      Celery Worker (optional)           │
└─────────────────────────────────────────┘
```

