from rest_framework import serializers
from .models import MLModel

class MLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModel
        fields = [
            "id",
            "company",
            "name",
            "version",
            "model_type",
            "description",
            "trained_at",
            "training_fields",
            "prediction_fields",
            "records_per_account",
            "active",
        ]
        read_only_fields = ["id", "version", "trained_at"]
