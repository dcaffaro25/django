from rest_framework import serializers

class AskSerializer(serializers.Serializer):
    query = serializers.CharField()
    k_each = serializers.IntegerField(required=False, min_value=1, max_value=50)
    temperature = serializers.FloatField(required=False, min_value=0, max_value=2)
    num_predict = serializers.IntegerField(required=False, min_value=16, max_value=1024)
