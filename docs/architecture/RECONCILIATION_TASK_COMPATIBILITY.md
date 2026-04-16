# Reconciliation Task Compatibility

## Overview

The new centralized task management system is **fully compatible** with the existing reconciliation task management system. Both systems operate independently and complement each other.

## Two Separate Systems

### 1. Legacy Reconciliation Task Management (Intact)

**Location:** `accounting/views.py` → `ReconciliationTaskViewSet`

**Model:** `ReconciliationTask` (in `accounting/models.py`)

**Endpoints:**
- `POST /reconciliation-tasks/start/` - Start a reconciliation task
- `GET /reconciliation-tasks/` - List reconciliation tasks
- `GET /reconciliation-tasks/{id}/` - Get reconciliation task details
- `POST /reconciliation-tasks/{id}/cancel/` - Cancel a reconciliation task
- `GET /reconciliation-tasks/queued/` - Get queued tasks with live Celery info
- `GET /reconciliation-tasks/task_counts/` - Get task counts by status

**Features:**
- Tracks reconciliation-specific metadata (config, pipeline, suggestions, stats)
- Has its own status field (`queued`, `running`, `completed`, `failed`, `cancelled`)
- Uses its own cancel logic that calls `current_app.control.revoke()`
- Provides reconciliation-specific statistics and monitoring

**Status:** ✅ **Fully intact and unchanged**

### 2. New Centralized Task Management

**Location:** `core/task_views.py` → `TaskListView`, `TaskStopView`, etc.

**Model:** `Job` (in `core/models.py`) - automatically populated via Celery hooks

**Endpoints:**
- `GET /api/tasks/` - List all tasks (including reconciliation)
- `GET /api/tasks/{task_id}/` - Get task details
- `POST /api/tasks/{task_id}/stop/` - Stop any task (soft/hard)
- `GET /api/tasks/statistics/` - Get statistics
- `GET /api/tasks/types/` - Get available task types

**Features:**
- Automatically tracks ALL Celery tasks via celery hooks
- Provides unified view across all task types
- Can filter by task type (including `reconciliation`)
- Provides soft/hard stop functionality

**Status:** ✅ **Operates alongside legacy system**

## How They Work Together

### Automatic Tracking

When a reconciliation task is started:

1. **Legacy System:**
   - Creates `ReconciliationTask` record
   - Calls `compare_two_engines_task.delay()` or `match_many_to_many_task.delay()`
   - Stores Celery `task_id` in `ReconciliationTask.task_id`

2. **New System (Automatic):**
   - Celery hooks automatically create `Job` record
   - Task type is detected as `reconciliation` based on task name
   - Stored in `Job.meta['task_type']` and `Job.kind`

### Task Type Detection

Reconciliation tasks are automatically categorized as `reconciliation` type:

- `accounting.tasks.compare_two_engines_task` → `reconciliation`
- `accounting.tasks.match_many_to_many_task` → `reconciliation`
- Any task starting with `accounting.tasks.` → `reconciliation`

### Viewing Reconciliation Tasks

**Via Legacy System:**
```bash
GET /reconciliation-tasks/?tenant_id=4&status=running
```

**Via New System:**
```bash
GET /api/tasks/?task_type=reconciliation&company_id=4&state=STARTED
```

### Stopping Reconciliation Tasks

**Via Legacy System:**
```bash
POST /reconciliation-tasks/{id}/cancel/
{
  "reason": "User requested cancellation"
}
```
- Updates `ReconciliationTask.status` to `cancelled`
- Calls `current_app.control.revoke(task_id, terminate=True)`
- Updates `ReconciliationTask.error_message`

**Via New System:**
```bash
POST /api/tasks/{task_id}/stop/
{
  "hard": true  # or false for soft stop
}
```
- Updates `Job.state` to `REVOKED`
- Calls `current_app.control.revoke(task_id, terminate=hard)`
- Updates `Job.error` field

**Note:** Both methods work on the same underlying Celery task. The legacy system provides reconciliation-specific context, while the new system provides a unified interface.

## No Conflicts

The two systems are designed to work together:

1. **Different Models:** `ReconciliationTask` vs `Job` - no database conflicts
2. **Different Endpoints:** `/reconciliation-tasks/` vs `/api/tasks/` - no URL conflicts
3. **Different Purposes:**
   - Legacy: Reconciliation-specific tracking and management
   - New: Unified task management across all task types
4. **Same Underlying Celery Tasks:** Both can stop the same task, but they update different models

## Best Practices

### For Reconciliation-Specific Operations

Use the **legacy system** (`/reconciliation-tasks/`):
- Starting reconciliation tasks
- Viewing reconciliation-specific metadata (config, pipeline, suggestions)
- Reconciliation-specific statistics
- Reconciliation-specific cancellation with reason

### For Unified Task Management

Use the **new system** (`/api/tasks/`):
- Viewing all tasks across the system
- Filtering by task type (including reconciliation)
- Unified statistics across all task types
- Quick task stopping without reconciliation-specific context

### Example: Monitoring Reconciliation Tasks

**Reconciliation-Specific View:**
```bash
GET /reconciliation-tasks/queued/?tenant_id=4
```
Returns:
- DB tasks with reconciliation metadata
- Live Celery queue info
- Reconciliation-specific status

**Unified View:**
```bash
GET /api/tasks/?task_type=reconciliation&company_id=4
```
Returns:
- All reconciliation tasks with unified format
- Can be combined with other task types
- Provides consistent API across all task types

## Migration Path

If you want to migrate to the new system:

1. **Keep using legacy endpoints** for reconciliation-specific operations
2. **Use new endpoints** for unified monitoring and management
3. **Both systems will continue to work** - no breaking changes
4. **Gradually adopt new system** for new features

## Summary

✅ **Legacy reconciliation task management is fully intact**
✅ **New system complements (does not replace) legacy system**
✅ **Both systems can be used simultaneously**
✅ **No conflicts or breaking changes**
✅ **Reconciliation tasks are automatically categorized in new system**

