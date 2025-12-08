# core/task_views.py
"""
Centralized Task Management API Views

Provides REST API endpoints for:
- Listing tasks with filtering
- Getting task details
- Stopping tasks (soft/hard)
- Task statistics
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import permissions
from django.conf import settings

from .task_manager import TaskManager

logger = __import__('logging').getLogger(__name__)


class TaskListView(APIView):
    """
    List tasks with filtering options.
    
    GET /api/tasks/
    
    Query Parameters:
        - task_type: Filter by task type (etl, import_template, etc.)
        - state: Filter by state (PENDING, STARTED, SUCCESS, etc.)
        - company_id: Filter by company ID
        - tenant_id: Filter by tenant ID
        - created_by_id: Filter by user ID
        - hours_ago: Only show tasks from last N hours
        - limit: Maximum number of results (default: 100)
        - offset: Offset for pagination (default: 0)
        - order_by: Order by field (default: -created_at)
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        # Extract query parameters
        task_type = request.query_params.get('task_type')
        state = request.query_params.get('state')
        company_id = request.query_params.get('company_id')
        tenant_id = request.query_params.get('tenant_id')
        created_by_id = request.query_params.get('created_by_id')
        hours_ago = request.query_params.get('hours_ago')
        limit = int(request.query_params.get('limit', 100))
        offset = int(request.query_params.get('offset', 0))
        order_by = request.query_params.get('order_by', '-created_at')
        
        # Convert company_id to int if provided
        if company_id:
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                company_id = None
        
        # Convert created_by_id to int if provided
        if created_by_id:
            try:
                created_by_id = int(created_by_id)
            except (ValueError, TypeError):
                created_by_id = None
        
        # Convert hours_ago to int if provided
        if hours_ago:
            try:
                hours_ago = int(hours_ago)
            except (ValueError, TypeError):
                hours_ago = None
        
        # Get tasks
        result = TaskManager.list_tasks(
            task_type=task_type,
            state=state,
            company_id=company_id,
            tenant_id=tenant_id,
            created_by_id=created_by_id,
            hours_ago=hours_ago,
            limit=limit,
            offset=offset,
            order_by=order_by
        )
        
        return Response(result, status=status.HTTP_200_OK)


class TaskDetailView(APIView):
    """
    Get detailed information about a specific task.
    
    GET /api/tasks/{task_id}/
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, task_id: str):
        task = TaskManager.get_task(task_id)
        
        if task is None:
            return Response(
                {'error': f'Task {task_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        return Response(task, status=status.HTTP_200_OK)


class TaskStopView(APIView):
    """
    Stop a running task (soft or hard stop).
    
    POST /api/tasks/{task_id}/stop/
    
    Body (optional):
        {
            "hard": true  // If true, hard stop (terminate). If false or omitted, soft stop (revoke).
        }
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, task_id: str):
        hard = request.data.get('hard', False)
        
        result = TaskManager.stop_task(task_id, hard=hard)
        
        if result['success']:
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class TaskStatisticsView(APIView):
    """
    Get task statistics.
    
    GET /api/tasks/statistics/
    
    Query Parameters:
        - task_type: Filter by task type
        - company_id: Filter by company ID
        - hours_ago: Time window for statistics (default: 24)
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        task_type = request.query_params.get('task_type')
        company_id = request.query_params.get('company_id')
        hours_ago = request.query_params.get('hours_ago', 24)
        
        # Convert company_id to int if provided
        if company_id:
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                company_id = None
        
        # Convert hours_ago to int if provided
        if hours_ago:
            try:
                hours_ago = int(hours_ago)
            except (ValueError, TypeError):
                hours_ago = 24
        
        stats = TaskManager.get_statistics(
            task_type=task_type,
            company_id=company_id,
            hours_ago=hours_ago
        )
        
        return Response(stats, status=status.HTTP_200_OK)


class TaskTypesView(APIView):
    """
    Get list of available task types.
    
    GET /api/tasks/types/
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        types = TaskManager.get_available_task_types()
        return Response({'task_types': types}, status=status.HTTP_200_OK)

