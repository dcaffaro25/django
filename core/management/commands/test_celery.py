# core/management/commands/test_celery.py
"""
Management command to test Celery connectivity and task execution.

This command helps verify that your local Celery setup is working correctly
with the homologation database.

Usage:
------
    # Basic connectivity test
    python manage.py test_celery
    
    # Test with a specific task
    python manage.py test_celery --task accounting.tasks.recalculate_status_task
    
    # Test with timeout
    python manage.py test_celery --timeout 30
    
    # Test async mode (don't wait for result)
    python manage.py test_celery --async
"""

from __future__ import annotations
import time
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = "Test Celery connectivity and task execution"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--task',
            default='nord_backend.celery.debug_task',
            help='Task to test (default: debug_task)'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30,
            help='Timeout in seconds (default: 30)'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            dest='async_mode',
            help='Async mode - dispatch task without waiting for result'
        )
        parser.add_argument(
            '--queue',
            default='celery',
            help='Queue to send task to (default: celery)'
        )
    
    def handle(self, *args, **options):
        from celery import current_app
        from celery.result import AsyncResult
        
        task_name = options['task']
        timeout = options['timeout']
        async_mode = options['async_mode']
        queue = options['queue']
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("CELERY CONNECTIVITY TEST"))
        self.stdout.write("=" * 60)
        
        # Show configuration
        self.stdout.write(f"\nConfiguration:")
        self.stdout.write(f"  Broker URL: {settings.CELERY_BROKER_URL}")
        self.stdout.write(f"  Result Backend: {settings.CELERY_RESULT_BACKEND}")
        self.stdout.write(f"  Eager Mode: {getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False)}")
        self.stdout.write(f"  Local Mode: {getattr(settings, 'LOCAL_MODE', False)}")
        self.stdout.write(f"  Environment: {getattr(settings, 'ENVIRONMENT_MODE', 'unknown')}")
        
        # Test broker connection
        self.stdout.write(f"\n1. Testing broker connection...")
        try:
            # Try to get broker connection
            with current_app.connection() as conn:
                conn.ensure_connection(max_retries=3)
            self.stdout.write(self.style.SUCCESS("   ✓ Broker connection OK"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Broker connection FAILED: {e}"))
            self.stdout.write("\n   Suggestions:")
            self.stdout.write("   - Make sure Redis is running: docker run -d -p 6379:6379 redis:alpine")
            self.stdout.write("   - Check LOCAL_REDIS_URL in local_credentials.ini")
            return
        
        # Send test task
        self.stdout.write(f"\n2. Sending test task: {task_name}")
        self.stdout.write(f"   Queue: {queue}")
        
        try:
            # Get the task
            task = current_app.tasks.get(task_name)
            if not task:
                # Try to import it
                parts = task_name.rsplit('.', 1)
                if len(parts) == 2:
                    module_name, func_name = parts
                    import importlib
                    module = importlib.import_module(module_name)
                    task = getattr(module, func_name)
            
            if not task:
                raise CommandError(f"Task not found: {task_name}")
            
            # Dispatch the task
            start_time = time.time()
            result = task.apply_async(queue=queue)
            task_id = result.id
            
            self.stdout.write(f"   Task ID: {task_id}")
            self.stdout.write(self.style.SUCCESS("   ✓ Task dispatched successfully"))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Failed to dispatch task: {e}"))
            return
        
        if async_mode:
            self.stdout.write(f"\n3. Async mode - not waiting for result")
            self.stdout.write(f"   Check task status with: python manage.py test_celery --task-id {task_id}")
            return
        
        # Wait for result
        self.stdout.write(f"\n3. Waiting for result (timeout: {timeout}s)...")
        
        try:
            async_result = AsyncResult(task_id)
            
            # Poll for result
            waited = 0
            poll_interval = 1.0
            
            while waited < timeout:
                state = async_result.state
                self.stdout.write(f"   State: {state} ({waited}s elapsed)")
                
                if state == 'SUCCESS':
                    result_value = async_result.get()
                    elapsed = time.time() - start_time
                    
                    self.stdout.write(self.style.SUCCESS(f"\n   ✓ Task completed in {elapsed:.2f}s"))
                    self.stdout.write(f"   Result: {json.dumps(result_value, indent=2, default=str)}")
                    break
                
                elif state == 'FAILURE':
                    error = async_result.result
                    self.stdout.write(self.style.ERROR(f"\n   ✗ Task failed: {error}"))
                    break
                
                elif state == 'REVOKED':
                    self.stdout.write(self.style.WARNING(f"\n   ! Task was revoked"))
                    break
                
                time.sleep(poll_interval)
                waited += poll_interval
            
            else:
                self.stdout.write(self.style.WARNING(f"\n   ! Timeout - task still in state: {async_result.state}"))
                self.stdout.write("   The task may still be running. Check Celery worker logs.")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error waiting for result: {e}"))
        
        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("TEST COMPLETE")
        self.stdout.write("=" * 60)
        
        self.stdout.write("\nTo run a full test with a real task:")
        self.stdout.write("  python manage.py test_celery --task accounting.tasks.recalculate_status_task")
        self.stdout.write("\nTo test reconciliation tasks:")
        self.stdout.write("  python manage.py test_celery --task accounting.tasks.match_many_to_many_task")

