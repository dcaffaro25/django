from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
#from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    FinancialIndex, IndexQuote, FinancialIndexQuoteForecast,
    get_next_n_occurrences, get_previous_n_occurrences, get_occurrences_between
)
from .serializers import (
    FinancialIndexSerializer,
    IndexQuoteSerializer,
    FinancialIndexQuoteForecastSerializer,
    FinancialIndexMiniSerializer,
    IndexQuoteMiniSerializer
)
from datetime import datetime

# core/views.py
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.utils import timezone
from datetime import timedelta

from core.models import ActionEvent
from core.serializers import ActionEventSerializer, TaskResultSerializer

from django_celery_results.models import TaskResult
from django.conf import settings

# import your Celery app
from celery import app as celery_app, current_app
from .models import Job

class JobStatusView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, task_id: str):
        try:
            job = Job.objects.get(task_id=task_id)
            payload = {
                "task_id": job.task_id,
                "state": job.state,        # one of your STATE_MAP values
                "kind": job.kind,
                "queue": job.queue,
                "worker": job.worker,
                "created_at": job.created_at,
                "enqueued_at": job.enqueued_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "retries": job.retries,
                "max_retries": job.max_retries,
                "total": job.total,
                "done": job.done,
                "percent": job.percent,
                "by_category": job.by_category,
                "result": job.result if job.state == "SUCCESS" else None,
                "error": job.error if job.state in ("FAILURE","REVOKED") else None,
            }
            return Response(payload, status=200)
        except Job.DoesNotExist:
            # fallback to raw celery state if we somehow missed hooks
            res = current_app.AsyncResult(task_id)
            return Response(
                {"task_id": task_id, "state": res.state or "PENDING"},
                status=200
            )

class JobListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = Job.objects.all().order_by("-created_at")
        if kind := request.query_params.get("kind"):
            qs = qs.filter(kind=kind)
        if state := request.query_params.get("state"):
            qs = qs.filter(state=state)
        if tenant_id := request.query_params.get("tenant_id"):
            qs = qs.filter(tenant_id=tenant_id)

        limit = int(request.query_params.get("limit", 50))
        qs = qs[:max(1, min(limit, 200))]

        data = [{
            "task_id": j.task_id,
            "state": j.state,
            "kind": j.kind,
            "queue": j.queue,
            "worker": j.worker,
            "created_at": j.created_at,
            "started_at": j.started_at,
            "finished_at": j.finished_at,
            "percent": j.percent,
            "total": j.total,
            "done": j.done,
            "by_category": j.by_category,
            "error": j.error if j.state in ("FAILURE","REVOKED") else None,
        } for j in qs]
        return Response({"results": data}, status=200)
    
    
class JobCancelView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request, task_id: str):
        current_app.control.revoke(task_id, terminate=True)
        # state will flip to REVOKED by signal
        return Response({"task_id": task_id, "revoked": True}, status=200)
    

class ActivityFeedView(ListAPIView):
    """Latest actions (admin-like). Query params: company_id, level, limit, since_hours."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ActionEventSerializer

    def get_queryset(self):
        qs = ActionEvent.objects.all().order_by("-created_at")
        company_id  = self.request.query_params.get("company_id")
        level       = self.request.query_params.get("level")
        since_hours = int(self.request.query_params.get("since_hours", "168"))  # default 7 days
        if company_id: qs = qs.filter(company_id=company_id)
        if level: qs = qs.filter(level=level)
        if since_hours > 0:
            qs = qs.filter(created_at__gte=timezone.now() - timedelta(hours=since_hours))
        limit = int(self.request.query_params.get("limit", "200"))
        return qs[:limit]


class CeleryQueuesView(APIView):
    """List workers and their tasks: active/reserved/scheduled."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        i = celery_app.control.inspect()
        data = {
            "workers": list((i.ping() or {}).keys()) if i else [],
            "active": i.active() or {},
            "reserved": i.reserved() or {},
            "scheduled": i.scheduled() or {},
            "stats": i.stats() or {},
            "registered": i.registered() or {},
            "conf": {"broker_url": getattr(settings, "CELERY_BROKER_URL", None)},
        }
        return Response(data)


class CeleryResultsView(ListAPIView):
    """Recent task results (success/fail). Query: name, status, hours, limit"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TaskResultSerializer

    def get_queryset(self):
        qs = TaskResult.objects.all().order_by("-date_done")
        name   = self.request.query_params.get("name")
        status = self.request.query_params.get("status")
        hours  = int(self.request.query_params.get("hours","168"))
        if name: qs = qs.filter(task_name=name)
        if status: qs = qs.filter(status=status.upper())
        if hours > 0:
            qs = qs.filter(date_done__gte=timezone.now() - timedelta(hours=hours))
        limit = int(self.request.query_params.get("limit","200"))
        return qs[:limit]


class CeleryTaskControlView(APIView):
    """
    POST /api/celery/tasks/{task_id}/revoke
    POST /api/celery/tasks/{task_id}/bump
      Body: {"queue":"imports_high"}  # or {"priority": 9} if using AMQP priority
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, task_id: str, action: str):
        if action == "revoke":
            terminate = bool(request.data.get("terminate", False))
            celery_app.control.revoke(task_id, terminate=terminate)
            return Response({"ok": True, "task_id": task_id, "action": "revoked"})
        elif action == "bump":
            # Strategy: revoke if pending, then re-enqueue to high-priority queue or with priority header
            target_queue = request.data.get("queue", "high_priority")
            priority     = request.data.get("priority")  # AMQP only
            # Try to read original TaskResult to recreate call (best effort)
            tr = TaskResult.objects.filter(task_id=task_id).order_by("-date_done").first()
            if tr and tr.task_name:
                # We assume the original args/kwargs are stored in result/meta; adjust if you store elsewhere
                args   = tr.meta.get("args", []) if isinstance(tr.meta, dict) else []
                kwargs = tr.meta.get("kwargs", {}) if isinstance(tr.meta, dict) else {}
                celery_app.control.revoke(task_id, terminate=False)
                sig = celery_app.signature(tr.task_name, args=args, kwargs=kwargs)
                opts = {}
                if priority is not None: opts["priority"] = int(priority)  # RabbitMQ/AMQP
                if target_queue: opts["queue"] = target_queue
                new_id = sig.apply_async(**opts).id
                return Response({"ok": True, "old_task_id": task_id, "new_task_id": new_id,
                                 "routed_to": target_queue, "priority": opts.get("priority")})
            # Fallback: try broker-level move (not generally supported), so return 400
            return Response({"ok": False, "error": "Cannot reconstruct task; resend manually"}, status=400)
        else:
            return Response({"ok": False, "error": "Unknown action"}, status=400)


class FinancialIndexViewSet(viewsets.ModelViewSet):
    queryset = FinancialIndex.objects.all()
    serializer_class = FinancialIndexSerializer
    #filter_backends = [DjangoFilterBackend]
    filterset_fields = ['code', 'index_type']

    @action(detail=True, methods=['get'])
    def quotes(self, request, pk=None):
        index = self.get_object()
        quotes = index.quotes.all()
        use_mini = request.query_params.get("mini", "false") == "true"
        serializer = IndexQuoteMiniSerializer(quotes, many=True) if use_mini else IndexQuoteSerializer(quotes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def forecast(self, request, pk=None):
        index = self.get_object()
        forecasts = index.forecast_quotes.all()
        serializer = FinancialIndexQuoteForecastSerializer(forecasts, many=True)
        return Response(serializer.data)


class IndexQuoteViewSet(viewsets.ModelViewSet):
    queryset = IndexQuote.objects.all()
    serializer_class = IndexQuoteSerializer
    #filter_backends = [DjangoFilterBackend]
    filterset_fields = ['index', 'date']


class FinancialIndexQuoteForecastViewSet(viewsets.ModelViewSet):
    queryset = FinancialIndexQuoteForecast.objects.all()
    serializer_class = FinancialIndexQuoteForecastSerializer
    #filter_backends = [DjangoFilterBackend]
    filterset_fields = ['index', 'date']


class RecurrencePreviewView(APIView):
    def get(self, request):
        try:
            rrule_str = request.query_params.get("rrule")
            dtstart_str = request.query_params.get("dtstart")
            after_str = request.query_params.get("after")
            n = int(request.query_params.get("n", 10))

            if not rrule_str or not dtstart_str:
                return Response({"error": "Missing 'rrule' or 'dtstart' parameters"}, status=400)

            dtstart = datetime.fromisoformat(dtstart_str)
            after = datetime.fromisoformat(after_str) if after_str else None

            dates = get_next_n_occurrences(rrule_str, dtstart, n, after)
            return Response({"occurrences": [d.isoformat() for d in dates]})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class RecurrencePreviousView(APIView):
    def get(self, request):
        try:
            rrule_str = request.query_params.get("rrule")
            dtstart_str = request.query_params.get("dtstart")
            before_str = request.query_params.get("before")
            n = int(request.query_params.get("n", 10))

            if not rrule_str or not dtstart_str:
                return Response({"error": "Missing 'rrule' or 'dtstart' parameters"}, status=400)

            dtstart = datetime.fromisoformat(dtstart_str)
            before = datetime.fromisoformat(before_str) if before_str else None

            dates = get_previous_n_occurrences(rrule_str, dtstart, n, before)
            return Response({"occurrences": [d.isoformat() for d in dates]})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class RecurrenceRangeView(APIView):
    def get(self, request):
        try:
            rrule_str = request.query_params.get("rrule")
            dtstart = datetime.fromisoformat(request.query_params.get("dtstart"))
            start = datetime.fromisoformat(request.query_params.get("start"))
            end = datetime.fromisoformat(request.query_params.get("end"))

            occurrences = get_occurrences_between(rrule_str, dtstart, start, end)
            return Response({"occurrences": [d.isoformat() for d in occurrences]})
        except Exception as e:
            return Response({"error": str(e)}, status=400)


class TutorialView(APIView):
    """
    Tutorial endpoint that returns tutorial steps in HTML format suitable for a wizard component.
    
    Query parameters:
    - audience: 'user', 'developer', or omit for all
    - format: 'json' (default) or 'html'
    - step_id: Optional, get a specific step by ID
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        from .tutorial_data import get_tutorial_steps, get_tutorial_step
        
        audience = request.query_params.get('audience')
        format_type = request.query_params.get('format', 'json')
        step_id = request.query_params.get('step_id')
        
        # Get specific step if requested
        if step_id:
            step = get_tutorial_step(step_id)
            if not step:
                return Response(
                    {"error": f"Tutorial step '{step_id}' not found"},
                    status=404
                )
            steps = [step]
        else:
            # Get all steps (optionally filtered by audience)
            steps = get_tutorial_steps(audience)
        
        # Return HTML format if requested
        if format_type == 'html':
            from django.http import HttpResponse
            html_content = self._generate_html(steps, audience)
            return HttpResponse(html_content, content_type='text/html')
        
        # Return JSON format (default)
        return Response({
            "count": len(steps),
            "audience": audience,
            "steps": steps
        })
    
    def _generate_html(self, steps, audience_filter):
        """Generate a complete HTML page with all tutorial steps."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NORD Accounting System - Tutorial</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f6f6f6;
        }
        .tutorial-container {
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .wizard-step {
            margin-bottom: 40px;
            padding-bottom: 40px;
            border-bottom: 2px solid #e5e5e5;
        }
        .wizard-step:last-child {
            border-bottom: none;
        }
        .wizard-step h2 {
            color: #025736;
            margin-top: 0;
            font-size: 28px;
            border-bottom: 3px solid #025736;
            padding-bottom: 10px;
        }
        .wizard-step h3 {
            color: #059669;
            margin-top: 25px;
            font-size: 20px;
        }
        .wizard-step p {
            margin: 15px 0;
            font-size: 16px;
        }
        .wizard-step ul, .wizard-step ol {
            margin: 15px 0;
            padding-left: 30px;
        }
        .wizard-step li {
            margin: 8px 0;
            font-size: 15px;
        }
        .wizard-step code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 14px;
        }
        .wizard-step pre {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            margin: 15px 0;
        }
        .wizard-step pre code {
            background: transparent;
            color: inherit;
            padding: 0;
        }
        .step-meta {
            display: inline-block;
            background: #e5e5e5;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            margin-bottom: 15px;
            color: #666;
        }
        .step-meta.user {
            background: #dbeafe;
            color: #1e40af;
        }
        .step-meta.developer {
            background: #fef3c7;
            color: #92400e;
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        .header h1 {
            color: #025736;
            font-size: 36px;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
            font-size: 18px;
        }
    </style>
</head>
<body>
    <div class="tutorial-container">
        <div class="header">
            <h1>NORD Accounting System - Complete Tutorial</h1>
            <p>Comprehensive guide for users and developers</p>
        </div>
"""
        
        for step in steps:
            audience_badge = step.get('audience', 'all')
            html += f"""
        <div class="wizard-step" data-audience="{step.get('audience')}" data-step-id="{step.get('id')}">
            <span class="step-meta {audience_badge}">{audience_badge.upper()}</span>
            {step.get('html', '')}
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        return html