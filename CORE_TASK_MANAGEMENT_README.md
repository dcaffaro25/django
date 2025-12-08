# Centralized Celery Task Management System

## Overview

A comprehensive, centralized task management system for Celery tasks with filtering, monitoring, and control capabilities. Built on top of the existing `Job` model for backwards compatibility.

## Features

- **Task Type Filtering**: Filter tasks by type (etl, import_template, integration_rule, email, ml_training, etc.)
- **Soft Stop**: Gracefully revoke tasks (allows current operation to complete)
- **Hard Stop**: Immediately terminate running tasks
- **Real-time Status**: Live Celery state combined with database tracking
- **Statistics**: Aggregate statistics by task type, state, company, etc.
- **Backwards Compatible**: Uses existing `Job` model and celery hooks

## API Endpoints

### List Tasks
```
GET /api/tasks/
```

**Query Parameters:**
- `task_type`: Filter by task type (etl, import_template, etc.)
- `state`: Filter by state (PENDING, STARTED, SUCCESS, FAILURE, etc.)
- `company_id`: Filter by company ID
- `tenant_id`: Filter by tenant ID
- `created_by_id`: Filter by user ID
- `hours_ago`: Only show tasks from last N hours
- `limit`: Maximum results (default: 100)
- `offset`: Pagination offset (default: 0)
- `order_by`: Order field (default: -created_at)

**Example:**
```
GET /api/tasks/?task_type=etl&state=STARTED&company_id=4&limit=50
```

### Get Task Details
```
GET /api/tasks/{task_id}/
```

**Example:**
```
GET /api/tasks/abc123-def456-ghi789/
```

### Stop Task
```
POST /api/tasks/{task_id}/stop/
```

**Body (optional):**
```json
{
  "hard": false  // true for hard stop, false (default) for soft stop
}
```

**Example - Soft Stop:**
```
POST /api/tasks/abc123-def456-ghi789/stop/
```

**Example - Hard Stop:**
```
POST /api/tasks/abc123-def456-ghi789/stop/
{
  "hard": true
}
```

### Get Statistics
```
GET /api/tasks/statistics/
```

**Query Parameters:**
- `task_type`: Filter by task type
- `company_id`: Filter by company ID
- `hours_ago`: Time window (default: 24)

**Example:**
```
GET /api/tasks/statistics/?task_type=etl&company_id=4&hours_ago=48
```

### Get Available Task Types
```
GET /api/tasks/types/
```

Returns list of all available task types with display names.

## Task Types

The system automatically categorizes tasks based on their task name:

- **etl**: ETL Pipeline tasks (`etl.process_etl_file`, `etl.process_etl_batch`)
- **import_template**: Import Template tasks (`import.process_import_template`, `import.process_import_batch`)
- **integration_rule**: Integration Rule tasks
- **email**: Email tasks
- **ml_training**: ML Training tasks
- **embedding**: Embedding tasks
- **reconciliation**: Reconciliation tasks
- **other**: All other tasks

## Soft Stop vs Hard Stop

### Soft Stop (default)
- Revokes the task gracefully
- Allows current operation to complete
- Task will not be picked up by workers
- Use when you want to stop a task but allow it to finish current work

### Hard Stop
- Immediately terminates the running task
- Sends SIGTERM to the worker process
- May leave partial state
- Use only when absolutely necessary

## Backwards Compatibility

The system maintains full backwards compatibility:

1. **Existing Job Model**: Uses the existing `Job` model - no migrations needed
2. **Existing Celery Hooks**: Enhances existing hooks to automatically set `task_type`
3. **Existing Endpoints**: Legacy endpoints (`/jobs/`, `/jobs/{task_id}/`) still work
4. **Automatic Task Type Detection**: Task types are automatically determined from task names

## Implementation Details

### Task Type Detection

Task types are automatically determined from task names using pattern matching:
- Exact matches (e.g., `etl.process_etl_file` → `etl`)
- Prefix matches (e.g., any task starting with `etl.` → `etl`)
- Stored in `Job.meta['task_type']` for efficient filtering

### Database Integration

- Task type is stored in `Job.meta['task_type']` JSON field
- `Job.kind` field is also set to task_type for compatibility
- All existing indexes work with the new filtering

### Celery Integration

- Uses Celery's `control.revoke()` for stopping tasks
- Integrates with existing celery hooks for automatic tracking
- Falls back to Celery AsyncResult for tasks not in database

## Usage Examples

### Filter ETL tasks
```python
GET /api/tasks/?task_type=etl
```

### Get running tasks for a company
```python
GET /api/tasks/?company_id=4&state=STARTED
```

### Stop a running task gracefully
```python
POST /api/tasks/{task_id}/stop/
```

### Get statistics for last 48 hours
```python
GET /api/tasks/statistics/?hours_ago=48
```

## Response Format

### Task List Response
```json
{
  "tasks": [
    {
      "id": "uuid",
      "task_id": "celery-task-id",
      "task_name": "etl.process_etl_file",
      "task_type": "etl",
      "task_type_display": "ETL Pipeline",
      "state": "STARTED",
      "created_at": "2025-12-08T10:00:00Z",
      "started_at": "2025-12-08T10:00:01Z",
      "percent": 45.5,
      "total": 100,
      "done": 45,
      ...
    }
  ],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

### Task Detail Response
```json
{
  "id": "uuid",
  "task_id": "celery-task-id",
  "task_name": "etl.process_etl_file",
  "task_type": "etl",
  "task_type_display": "ETL Pipeline",
  "state": "STARTED",
  "live_state": "STARTED",
  "ready": false,
  "successful": false,
  "percent": 45.5,
  ...
}
```

### Statistics Response
```json
{
  "total": 500,
  "running": 5,
  "completed": 450,
  "failed": 40,
  "revoked": 5,
  "by_state": {
    "SUCCESS": 450,
    "FAILURE": 40,
    "STARTED": 3,
    "PENDING": 2
  },
  "by_task_type": {
    "etl": 200,
    "import_template": 150,
    "other": 150
  },
  "hours_ago": 24
}
```

