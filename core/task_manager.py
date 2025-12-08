# core/task_manager.py
"""
Centralized Celery Task Management System

Provides unified interface for:
- Task listing and filtering by type
- Soft stop (revoke without terminate) and hard stop (revoke with terminate)
- Task status monitoring
- Backwards compatibility with existing task tracking
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Count
from celery import current_app
from celery.result import AsyncResult

from .models import Job
from .constants import STATE_MAP

logger = logging.getLogger(__name__)


# Task type mapping based on task name patterns
TASK_TYPE_MAP = {
    # ETL tasks
    'etl.process_etl_file': 'etl',
    'etl.process_etl_batch': 'etl',
    'etl.': 'etl',  # Any task starting with 'etl.'
    
    # Import template tasks
    'import.process_import_template': 'import_template',
    'import.process_import_batch': 'import_template',
    'import.run_import_job': 'import_template',
    'import.': 'import_template',  # Any task starting with 'import.'
    
    # Integration rule tasks
    'multitenancy.tasks.execute_integration_rule': 'integration_rule',
    'multitenancy.tasks.trigger_integration_event': 'integration_rule',
    
    # Email tasks
    'multitenancy.tasks.send_user_invite_email': 'email',
    'multitenancy.tasks.send_user_email': 'email',
    
    # ML tasks
    'ML.tasks.train_model_task': 'ml_training',
    'ML.tasks.train_model_task2': 'ml_training',
    
    # Embedding tasks
    'accounting.tasks.generate_missing_embeddings': 'embedding',
    
    # Reconciliation tasks
    'accounting.tasks.compare_two_engines_task': 'reconciliation',
    'accounting.tasks.match_many_to_many_task': 'reconciliation',
    'accounting.tasks.': 'reconciliation',  # Any task starting with 'accounting.tasks.'
    
    # Other/unknown
    'default': 'other',
}


def get_task_type(task_name: str) -> str:
    """
    Determine task type from task name.
    
    Args:
        task_name: Full task name (e.g., 'etl.process_etl_file')
        
    Returns:
        Task type string (e.g., 'etl', 'import_template', 'other')
    """
    if not task_name:
        return 'other'
    
    # Check exact matches first
    if task_name in TASK_TYPE_MAP:
        return TASK_TYPE_MAP[task_name]
    
    # Check prefix matches
    for pattern, task_type in TASK_TYPE_MAP.items():
        if pattern.endswith('.') and task_name.startswith(pattern):
            return task_type
    
    return TASK_TYPE_MAP.get('default', 'other')


def get_task_type_display(task_type: str) -> str:
    """Get human-readable display name for task type."""
    display_map = {
        'etl': 'ETL Pipeline',
        'import_template': 'Import Template',
        'integration_rule': 'Integration Rule',
        'email': 'Email',
        'ml_training': 'ML Training',
        'embedding': 'Embedding',
        'reconciliation': 'Reconciliation',
        'other': 'Other',
    }
    return display_map.get(task_type, task_type.title())


class TaskManager:
    """
    Centralized task management interface.
    
    Provides methods for:
    - Listing and filtering tasks
    - Stopping tasks (soft/hard)
    - Getting task status
    - Task statistics
    """
    
    @staticmethod
    def list_tasks(
        task_type: Optional[str] = None,
        state: Optional[str] = None,
        company_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
        created_by_id: Optional[int] = None,
        hours_ago: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str = '-created_at'
    ) -> Dict[str, Any]:
        """
        List tasks with filtering options.
        
        Args:
            task_type: Filter by task type (etl, import_template, etc.)
            state: Filter by state (PENDING, STARTED, SUCCESS, etc.)
            company_id: Filter by company ID
            tenant_id: Filter by tenant ID
            created_by_id: Filter by user ID
            hours_ago: Only show tasks from last N hours
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Order by field (default: -created_at)
            
        Returns:
            Dict with 'tasks' list and 'total' count
        """
        qs = Job.objects.all()
        
        # Apply filters
        if task_type:
            # Filter by task_name pattern matching task_type
            task_names = [
                name for name, ttype in TASK_TYPE_MAP.items()
                if ttype == task_type and not name.endswith('.')
            ]
            # Also check prefix patterns
            prefix_patterns = [
                pattern for pattern, ttype in TASK_TYPE_MAP.items()
                if ttype == task_type and pattern.endswith('.')
            ]
            
            if task_names or prefix_patterns:
                q_filter = Q()
                for name in task_names:
                    q_filter |= Q(task_name=name)
                for pattern in prefix_patterns:
                    q_filter |= Q(task_name__startswith=pattern)
                qs = qs.filter(q_filter)
            else:
                # Fallback: try to match by kind field if it exists
                qs = qs.filter(kind=task_type)
        
        if state:
            qs = qs.filter(state=state)
        
        if company_id:
            # Note: Job model uses tenant_id, but we can also check meta
            qs = qs.filter(
                Q(tenant_id=str(company_id)) |
                Q(meta__company_id=company_id)
            )
        
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        
        if created_by_id:
            qs = qs.filter(created_by_id=created_by_id)
        
        if hours_ago:
            cutoff = timezone.now() - timedelta(hours=hours_ago)
            qs = qs.filter(created_at__gte=cutoff)
        
        # Get total count before pagination
        total = qs.count()
        
        # Apply ordering and pagination
        qs = qs.order_by(order_by)[offset:offset + limit]
        
        # Build response with task type information
        tasks = []
        for job in qs:
            task_type = get_task_type(job.task_name)
            task_data = {
                'id': str(job.id),
                'task_id': job.task_id,
                'task_name': job.task_name,
                'task_type': task_type,
                'task_type_display': get_task_type_display(task_type),
                'state': job.state,
                'kind': job.kind,
                'queue': job.queue,
                'worker': job.worker,
                'tenant_id': job.tenant_id,
                'created_by_id': job.created_by_id,
                'created_at': job.created_at.isoformat() if job.created_at else None,
                'enqueued_at': job.enqueued_at.isoformat() if job.enqueued_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'finished_at': job.finished_at.isoformat() if job.finished_at else None,
                'retries': job.retries,
                'max_retries': job.max_retries,
                'total': job.total,
                'done': job.done,
                'percent': job.percent,
                'by_category': job.by_category,
                'meta': job.meta,
                'result': job.result if job.state == STATE_MAP['SUCCESS'] else None,
                'error': job.error if job.state in (STATE_MAP['FAILURE'], STATE_MAP['REVOKED']) else None,
            }
            
            # Get live Celery state if task is still running
            if job.state in (STATE_MAP['PENDING'], STATE_MAP['SENT'], STATE_MAP['STARTED'], STATE_MAP['RETRY']):
                try:
                    ar = AsyncResult(job.task_id)
                    live_state = ar.state
                    if live_state and live_state != job.state:
                        task_data['live_state'] = live_state
                        task_data['live_info'] = ar.info if isinstance(ar.info, dict) else {}
                except Exception as e:
                    logger.debug(f"Could not get live state for task {job.task_id}: {e}")
            
            tasks.append(task_data)
        
        return {
            'tasks': tasks,
            'total': total,
            'limit': limit,
            'offset': offset,
        }
    
    @staticmethod
    def get_task(task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific task.
        
        Args:
            task_id: Celery task ID
            
        Returns:
            Dict with task details or None if not found
        """
        try:
            job = Job.objects.get(task_id=task_id)
        except Job.DoesNotExist:
            # Fallback to Celery AsyncResult
            try:
                ar = AsyncResult(task_id)
                return {
                    'task_id': task_id,
                    'task_name': ar.name or 'unknown',
                    'task_type': get_task_type(ar.name or ''),
                    'task_type_display': get_task_type_display(get_task_type(ar.name or '')),
                    'state': ar.state or 'PENDING',
                    'ready': ar.ready(),
                    'successful': ar.successful() if ar.ready() else False,
                    'result': ar.result if ar.ready() and ar.successful() else None,
                    'error': str(ar.info) if ar.ready() and not ar.successful() else None,
                    'in_db': False,
                }
            except Exception as e:
                logger.warning(f"Could not get task {task_id} from Celery: {e}")
                return None
        
        task_type = get_task_type(job.task_name)
        task_data = {
            'id': str(job.id),
            'task_id': job.task_id,
            'task_name': job.task_name,
            'task_type': task_type,
            'task_type_display': get_task_type_display(task_type),
            'state': job.state,
            'kind': job.kind,
            'queue': job.queue,
            'worker': job.worker,
            'tenant_id': job.tenant_id,
            'created_by_id': job.created_by_id,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'enqueued_at': job.enqueued_at.isoformat() if job.enqueued_at else None,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'finished_at': job.finished_at.isoformat() if job.finished_at else None,
            'retries': job.retries,
            'max_retries': job.max_retries,
            'total': job.total,
            'done': job.done,
            'percent': job.percent,
            'by_category': job.by_category,
            'meta': job.meta,
            'result': job.result if job.state == STATE_MAP['SUCCESS'] else None,
            'error': job.error if job.state in (STATE_MAP['FAILURE'], STATE_MAP['REVOKED']) else None,
            'in_db': True,
        }
        
        # Get live Celery state
        try:
            ar = AsyncResult(job.task_id)
            live_state = ar.state
            if live_state:
                task_data['live_state'] = live_state
                task_data['live_info'] = ar.info if isinstance(ar.info, dict) else {}
                task_data['ready'] = ar.ready()
                task_data['successful'] = ar.successful() if ar.ready() else False
        except Exception as e:
            logger.debug(f"Could not get live state for task {job.task_id}: {e}")
        
        return task_data
    
    @staticmethod
    def stop_task(task_id: str, hard: bool = False) -> Dict[str, Any]:
        """
        Stop a running task (soft or hard stop).
        
        Args:
            task_id: Celery task ID
            hard: If True, terminate the task immediately (hard stop).
                  If False, revoke the task gracefully (soft stop).
        
        Returns:
            Dict with operation result
        """
        try:
            # Check if task exists in database
            try:
                job = Job.objects.get(task_id=task_id)
                current_state = job.state
            except Job.DoesNotExist:
                current_state = None
            
            # Revoke the task in Celery
            current_app.control.revoke(task_id, terminate=hard)
            
            # Update database if task exists
            if current_state:
                Job.objects.filter(task_id=task_id).update(
                    state=STATE_MAP['REVOKED'],
                    finished_at=timezone.now(),
                    error=f"{'Hard stopped' if hard else 'Soft stopped'} by user",
                )
            
            return {
                'success': True,
                'task_id': task_id,
                'action': 'hard_stop' if hard else 'soft_stop',
                'message': f"Task {'terminated' if hard else 'revoked'} successfully",
            }
            
        except Exception as e:
            logger.exception(f"Error stopping task {task_id}: {e}")
            return {
                'success': False,
                'task_id': task_id,
                'error': str(e),
            }
    
    @staticmethod
    def get_statistics(
        task_type: Optional[str] = None,
        company_id: Optional[int] = None,
        hours_ago: Optional[int] = 24
    ) -> Dict[str, Any]:
        """
        Get task statistics.
        
        Args:
            task_type: Filter by task type
            company_id: Filter by company ID
            hours_ago: Time window for statistics
            
        Returns:
            Dict with statistics
        """
        qs = Job.objects.all()
        
        if hours_ago:
            cutoff = timezone.now() - timedelta(hours=hours_ago)
            qs = qs.filter(created_at__gte=cutoff)
        
        if company_id:
            # Try both string and integer matching for flexibility
            qs = qs.filter(
                Q(tenant_id=str(company_id)) |
                Q(tenant_id=company_id) |
                Q(meta__company_id=company_id) |
                Q(meta__company_id=str(company_id))
            )
        
        # Apply task_type filter if provided
        if task_type:
            task_names = [
                name for name, ttype in TASK_TYPE_MAP.items()
                if ttype == task_type and not name.endswith('.')
            ]
            prefix_patterns = [
                pattern for pattern, ttype in TASK_TYPE_MAP.items()
                if ttype == task_type and pattern.endswith('.')
            ]
            
            if task_names or prefix_patterns:
                q_filter = Q()
                for name in task_names:
                    q_filter |= Q(task_name=name)
                for pattern in prefix_patterns:
                    q_filter |= Q(task_name__startswith=pattern)
                # Also check meta.task_type field
                q_filter |= Q(meta__task_type=task_type)
                qs = qs.filter(q_filter)
            else:
                # Fallback: try to match by kind field or meta.task_type
                qs = qs.filter(Q(kind=task_type) | Q(meta__task_type=task_type))
        
        # Count by state
        state_counts = qs.values('state').annotate(count=Count('id'))
        state_stats = {item['state']: item['count'] for item in state_counts}
        
        # Count by task type
        all_tasks = qs.values('task_name')
        type_counts = {}
        for task in all_tasks:
            task_type_name = get_task_type(task['task_name'])
            type_counts[task_type_name] = type_counts.get(task_type_name, 0) + 1
        
        # Calculate totals
        total = qs.count()
        running = qs.filter(
            state__in=[STATE_MAP['PENDING'], STATE_MAP['SENT'], STATE_MAP['STARTED'], STATE_MAP['RETRY']]
        ).count()
        completed = qs.filter(state=STATE_MAP['SUCCESS']).count()
        failed = qs.filter(state=STATE_MAP['FAILURE']).count()
        revoked = qs.filter(state=STATE_MAP['REVOKED']).count()
        
        return {
            'total': total,
            'running': running,
            'completed': completed,
            'failed': failed,
            'revoked': revoked,
            'by_state': state_stats,
            'by_task_type': type_counts,
            'hours_ago': hours_ago,
        }
    
    @staticmethod
    def get_available_task_types() -> List[Dict[str, str]]:
        """Get list of available task types with display names."""
        types = set(TASK_TYPE_MAP.values())
        return [
            {
                'value': task_type,
                'display': get_task_type_display(task_type),
            }
            for task_type in sorted(types)
        ]

