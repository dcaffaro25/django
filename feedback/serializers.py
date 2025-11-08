"""
Serializers for the feedback app.
"""
from rest_framework import serializers

from . import models


class UserJudgmentSerializer(serializers.ModelSerializer):
    """Serializer to record a user judgment on a candidate."""
    class Meta:
        model = models.UserJudgment
        fields = ('id', 'candidate', 'accepted', 'edited_value', 'order')
        read_only_fields = ('id',)


class ModelVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ModelVersion
        fields = ('id', 'task', 'version_name', 'metrics', 'created_at')