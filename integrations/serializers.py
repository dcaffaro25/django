from rest_framework import serializers

from .models import ERPAPIDefinition, ERPConnection, ERPProvider


class ERPProviderMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ERPProvider
        fields = ["id", "slug", "name", "base_url"]


class ERPConnectionSerializer(serializers.ModelSerializer):
    provider_display = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ERPConnection
        fields = [
            "id",
            "provider",
            "provider_display",
            "company",
            "name",
            "app_key",
            "app_secret",
            "is_active",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "app_secret": {"write_only": True},
        }


class ERPConnectionListSerializer(serializers.ModelSerializer):
    """List view: mask app_key, never expose app_secret."""

    provider_display = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ERPConnection
        fields = [
            "id",
            "provider",
            "provider_display",
            "company",
            "name",
            "app_key_masked",
            "is_active",
        ]

    app_key_masked = serializers.SerializerMethodField()

    def get_app_key_masked(self, obj):
        if not obj.app_key:
            return ""
        if len(obj.app_key) <= 8:
            return "****"
        return obj.app_key[:4] + "…" + obj.app_key[-4:]


class ERPAPIDefinitionSerializer(serializers.ModelSerializer):
    provider_display = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ERPAPIDefinition
        fields = [
            "id",
            "provider",
            "provider_display",
            "call",
            "param_schema",
            "default_param",
            "description",
            "is_active",
        ]


class BuildPayloadRequestSerializer(serializers.Serializer):
    connection_id = serializers.IntegerField()
    api_definition_id = serializers.IntegerField()
    param_overrides = serializers.JSONField(required=False, default=dict)

