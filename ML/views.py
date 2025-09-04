from rest_framework.views import APIView
import io
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from datetime import timedelta
from .models import MLModel, MLTrainingTask
from .serializers import MLModelSerializer, MLTrainingTaskSerializer

from .tasks import train_model_task
from celery.result import AsyncResult

from .utils.train import (
    train_categorization_model,
    train_journal_model,
)
from .utils.predict import predict_top_accounts_with_names
from .utils.journal import suggest_journal_entries
from django.utils import timezone
from django.db.models import Count
from nord_backend.celery import app

class MLModelViewSet(viewsets.ModelViewSet):
    queryset = MLModel.objects.all().order_by("-trained_at")
    serializer_class = MLModelSerializer

    @action(detail=False, methods=["post"])
    def train(self, request, tenant_id=None):
        """
        Enqueue training as a background task & persist job record.
        """
        company_id = tenant_id#request.data.get("company_id")
        model_name = request.data.get("model_name")
        training_fields = request.data.get("training_fields")
        prediction_fields = request.data.get("prediction_fields")
        records_per_account = request.data.get("records_per_account")

        if not (company_id and model_name and training_fields and prediction_fields and records_per_account):
            return Response(
                {"error": "company_id, model_name, training_fields, prediction_fields, and records_per_account are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            records_per_account = int(records_per_account)
        except Exception:
            return Response({"error": "records_per_account must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Pre-create DB record with placeholder task_id
        task_obj = MLTrainingTask.objects.create(
            task_id="queued",
            #tenant_id=tenant_id,
            company_id=company_id,
            model_name=model_name,
            parameters=request.data,
            status="queued"
        )

        # 2. Trigger Celery, pass the db_id
        async_result = train_model_task.delay(task_obj.id, company_id, model_name, training_fields, prediction_fields, records_per_account)

        # 3. Update task_id
        task_obj.task_id = async_result.id
        task_obj.save(update_fields=["task_id"])

        return Response({
            "message": f"Training queued for {model_name}",
            "task_id": async_result.id,
            "db_id": task_obj.id,
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def predict(self, request, tenant_id=None):
        """
        Prediz a(s) conta(s) mais provável(is) para uma ou mais transações.
        Pode receber um único dict em 'transaction' ou uma lista em 'transactions'.
        Usa top_n para limitar o número de sugestões.
        """
        data = request.data
        model_id = data.get("model_id")
        company_id = tenant_id#data.get("company_id")
        transactions = data.get("transactions") or data.get("transaction")
        top_n = data.get("top_n", 3)

        try:
            top_n = int(top_n)
        except Exception:
            return Response({"error": "top_n must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if not transactions:
            return Response({"error": "No transaction data provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Seleção do modelo: via model_id ou último ativo da empresa
        if model_id:
            try:
                ml_model = MLModel.objects.get(id=model_id)
            except MLModel.DoesNotExist:
                return Response({"error": "Specified model_id does not exist"}, status=status.HTTP_404_NOT_FOUND)
        else:
            if not company_id:
                return Response({"error": "company_id is required when model_id is not provided"},
                                status=status.HTTP_400_BAD_REQUEST)
            ml_model = (
                MLModel.objects.filter(company_id=company_id, name="categorization", active=True)
                .order_by("-version")
                .first()
            )
            if not ml_model:
                return Response({"error": "No active categorisation model found for this company"},
                                status=status.HTTP_404_NOT_FOUND)

        # Normaliza para lista
        is_single = not isinstance(transactions, list)
        tx_list = transactions if isinstance(transactions, list) else [transactions]

        results = []
        for tx in tx_list:
            preds = predict_top_accounts_with_names(tx, ml_model, top_n=top_n)
            results.append(preds)
        return Response({"predictions": results if not is_single else results[0]})
    
    @action(detail=False, methods=["get"])
    def queued(self, request, tenant_id=None):
        """
        List persisted training tasks + live Celery state.
        """
        tenant_filter = tenant_id#request.query_params.get("tenant_id")
        status_filter = request.query_params.get("status")

        qs = MLTrainingTask.objects.all()
        if tenant_filter:
            qs = qs.filter(company_id=tenant_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

        db_tasks = MLTrainingTaskSerializer(qs, many=True).data

        try:
            i = app.control.inspect()
            live_info = {
                "active": i.active() or {},
                "reserved": i.reserved() or {},
                "scheduled": i.scheduled() or {}
            }
        except Exception as e:
            live_info = {"error": str(e)}

        return Response({"db_tasks": db_tasks, "celery_live": live_info})

    @action(detail=False, methods=["get"])
    def task_counts(self, request, tenant_id=None):
        """
        Counts by status, with filters.
        """
        tenant_filter = tenant_id#request.query_params.get("tenant_id")
        hours_ago = request.query_params.get("hours_ago")

        qs = MLTrainingTask.objects.all()

        if tenant_filter:
            qs = qs.filter(company_id=tenant_filter)
        if hours_ago:
            try:
                raw = str(hours_ago).lower()
                hours = int(raw[:-1]) * 24 if raw.endswith("d") else int(raw[:-1]) if raw.endswith("h") else int(raw)
                cutoff = timezone.now() - timedelta(hours=hours)
                qs = qs.filter(created_at__gte=cutoff)
            except ValueError:
                pass

        counts = qs.values("status").annotate(total=Count("id"))
        return Response({row["status"]: row["total"] for row in counts})