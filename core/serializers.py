from rest_framework import serializers
from .models import FinancialIndex, IndexQuote, FinancialIndexQuoteForecast


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