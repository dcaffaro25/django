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