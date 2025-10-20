from rest_framework import serializers
from .models import FinancialIndex, IndexQuote, FinancialIndexQuoteForecast, Job

# core/serializers.py
from rest_framework import serializers
from core.models import ActionEvent
from django_celery_results.models import TaskResult

class JobSerializer(serializers.ModelSerializer):
    percent = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "task_id", "task_name", "queue", "worker", "kind",
            "tenant_id", "created_by", "state",
            "created_at", "enqueued_at", "started_at", "finished_at",
            "eta", "expires", "retries", "max_retries", "priority",
            "total", "done", "percent", "by_category",
            "meta", "result", "error",
        ]

    def get_percent(self, obj):
        return obj.percent

class ActionEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    class Meta:
        model  = ActionEvent
        fields = ["id","company_id","actor_name","verb","level","message","meta",
                  "target_app","target_model","target_id","created_at"]
    def get_actor_name(self, obj):
        return getattr(obj.actor, "get_full_name", lambda: None)() or getattr(obj.actor,"username", None)

class TaskResultSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TaskResult
        fields = ["task_id","task_name","status","date_done","result","traceback","meta"]


class FinancialIndexSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialIndex
        fields = '__all__'


class IndexQuoteSerializer(serializers.ModelSerializer):
    index_code = serializers.ReadOnlyField(source='index.code')

    class Meta:
        model = IndexQuote
        fields = ['id', 'index', 'index_code', 'date', 'value']


class FinancialIndexQuoteForecastSerializer(serializers.ModelSerializer):
    index_code = serializers.ReadOnlyField(source='index.code')

    class Meta:
        model = FinancialIndexQuoteForecast
        fields = ['id', 'index', 'index_code', 'date', 'estimated_value', 'source']


#MINI

class FinancialIndexMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialIndex
        fields = ['id', 'code', 'name']

class IndexQuoteMiniSerializer(serializers.ModelSerializer):
    index = FinancialIndexMiniSerializer(read_only=True)

    class Meta:
        model = IndexQuote
        fields = ['id', 'index', 'date', 'value']

class FinancialIndexQuoteForecastMiniSerializer(serializers.ModelSerializer):
    index = FinancialIndexMiniSerializer(read_only=True)

    class Meta:
        model = FinancialIndexQuoteForecast
        fields = ['id', 'index', 'date', 'estimated_value']