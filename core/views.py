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
from celery import app as celery_app


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