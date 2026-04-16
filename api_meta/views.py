"""
Introspection / Meta-API views.

All endpoints are GET-only and designed for read-only consumption by
external agents (e.g. OpenClaw).  They auto-generate their responses from
the live codebase: models, URL router, serializers, filter sets, etc.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import registry

DOCS_ROOT = Path(settings.BASE_DIR) / "docs"


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


def _build_docs_tree(root: Path, prefix: str = "") -> list[dict]:
    """Walk *root* and return a list of doc entries with relative paths."""
    entries: list[dict] = []
    if not root.is_dir():
        return entries
    for item in sorted(root.iterdir()):
        rel = f"{prefix}{item.name}" if not prefix else f"{prefix}/{item.name}"
        if item.is_dir():
            children = _build_docs_tree(item, rel)
            if children:
                entries.append({
                    "name": item.name,
                    "path": rel,
                    "type": "directory",
                    "children": children,
                })
        elif item.suffix.lower() == ".md":
            stat = item.stat()
            entries.append({
                "name": item.name,
                "path": rel,
                "type": "file",
                "size_bytes": stat.st_size,
            })
    return entries


class MetaDocsListView(APIView):
    """GET /api/meta/docs/ — directory tree of all documentation markdown files."""

    def get(self, request):
        tree = _build_docs_tree(DOCS_ROOT)
        flat = []

        def _flatten(nodes: list[dict]):
            for node in nodes:
                if node["type"] == "file":
                    flat.append({"path": node["path"], "name": node["name"],
                                 "size_bytes": node["size_bytes"]})
                else:
                    _flatten(node.get("children", []))

        _flatten(tree)
        return Response({
            "docs_root": "docs/",
            "total_files": len(flat),
            "tree": tree,
            "files": flat,
        })


class MetaDocsDetailView(APIView):
    """GET /api/meta/docs/<path> — return the raw markdown content of a doc file."""

    def get(self, request, doc_path: str):
        target = (DOCS_ROOT / doc_path).resolve()

        if not str(target).startswith(str(DOCS_ROOT.resolve())):
            return Response(
                {"error": "Path traversal is not allowed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not target.is_file() or target.suffix.lower() != ".md":
            return Response(
                {"error": f"Document '{doc_path}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        content = target.read_text(encoding="utf-8")
        return Response({
            "path": doc_path,
            "name": target.name,
            "size_bytes": target.stat().st_size,
            "content": content,
        })
