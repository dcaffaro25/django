"""
Introspection / Meta-API views.

All endpoints are GET-only and designed for read-only consumption by
external agents (e.g. OpenClaw).  They auto-generate their responses from
the live codebase: models, URL router, serializers, filter sets, etc.
"""
from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import registry


class MetaEndpointsView(APIView):
    """GET /api/meta/endpoints — complete registry of all API endpoints."""

    def get(self, request):
        endpoints = registry.get_all_endpoints()
        return Response({"count": len(endpoints), "endpoints": endpoints})


class MetaModelsListView(APIView):
    """GET /api/meta/models — full data-model catalog."""

    def get(self, request):
        models = registry.get_all_models()
        return Response({"count": len(models), "models": models})


class MetaModelDetailView(APIView):
    """GET /api/meta/models/:modelName — detail for a single model."""

    def get(self, request, model_name: str):
        detail = registry.get_model_detail(model_name)
        if detail is None:
            return Response(
                {"error": f"Model '{model_name}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(detail)


class MetaModelRelationshipsView(APIView):
    """GET /api/meta/models/:modelName/relationships — relationship graph."""

    def get(self, request, model_name: str):
        rels = registry.get_model_relationships(model_name)
        if rels is None:
            return Response(
                {"error": f"Model '{model_name}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(rels)


class MetaEnumsView(APIView):
    """GET /api/meta/enums — every enum/allowed-value set."""

    def get(self, request):
        enums = registry.get_all_enums()
        return Response({"count": len(enums), "enums": enums})


class MetaFiltersView(APIView):
    """GET /api/meta/filters — filterable fields per endpoint."""

    def get(self, request):
        filters = registry.get_all_filters()
        return Response(filters)


class MetaCapabilitiesView(APIView):
    """GET /api/meta/capabilities — system capabilities overview."""

    def get(self, request):
        return Response(registry.get_capabilities())


class MetaHealthView(APIView):
    """GET /api/meta/health — health check."""
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({
            "status": "healthy",
            "api_version": "1.0.0",
            "timestamp": timezone.now().isoformat(),
            "service": "Nord Backend",
        })
