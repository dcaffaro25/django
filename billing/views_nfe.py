# -*- coding: utf-8 -*-
"""Views e endpoints para NFe: importação e CRUD + análise."""
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Sum, Count

from .models_nfe import NotaFiscal, NotaFiscalItem
from .serializers_nfe import (
    NotaFiscalSerializer,
    NotaFiscalListSerializer,
    NotaFiscalItemSerializer,
    NFeImportResultSerializer,
)
from .services.nfe_import_service import import_many
from multitenancy.mixins import ScopedQuerysetMixin

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1MB per file
MAX_FILES = settings.DATA_UPLOAD_MAX_NUMBER_FILES


class NFeImportView(APIView):
    """POST /api/nfe/import/ — upload de múltiplos XMLs (multipart/form-data, campo 'files')."""
    parser_classes = [MultiPartParser]

    def post(self, request, tenant_id=None):
        company = getattr(request, "tenant", None)
        if not company:
            return Response(
                {"detail": "Tenant (company) não identificado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {"detail": "Envie um ou mais arquivos XML no campo 'files'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(files) > MAX_FILES:
            return Response(
                {"detail": f"Máximo de {MAX_FILES} arquivos por requisição."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for f in files:
            if not (getattr(f, "name", "") or "").lower().endswith(".xml"):
                return Response(
                    {"detail": f"Arquivo '{getattr(f, 'name', '')}' não é .xml."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if f.size > MAX_FILE_SIZE_BYTES:
                return Response(
                    {"detail": f"Arquivo '{getattr(f, 'name', '')}' excede 1MB."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        result = import_many(files, company)
        serializer = NFeImportResultSerializer(result)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotaFiscalViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = NotaFiscal.objects.all()
    serializer_class = NotaFiscalSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["emit_cnpj", "dest_cnpj", "finalidade", "tipo_operacao", "numero", "serie"]

    def get_serializer_class(self):
        if self.action == "list":
            return NotaFiscalListSerializer
        return NotaFiscalSerializer

    @action(methods=["get"], detail=False, url_path="resumo")
    def resumo(self, request):
        """
        GET /api/nfe/resumo/?data_inicio=...&data_fim=...&emit_cnpj=...&dest_cnpj=...
        Retorna totais, soma por imposto, top emitentes, top produtos, distribuição por finalidade.
        """
        qs = self.get_queryset()
        data_inicio = request.query_params.get("data_inicio")
        data_fim = request.query_params.get("data_fim")
        emit_cnpj = request.query_params.get("emit_cnpj")
        dest_cnpj = request.query_params.get("dest_cnpj")
        if data_inicio:
            qs = qs.filter(data_emissao__date__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_emissao__date__lte=data_fim)
        if emit_cnpj:
            qs = qs.filter(emit_cnpj=emit_cnpj)
        if dest_cnpj:
            qs = qs.filter(dest_cnpj=dest_cnpj)

        total_nfs = qs.count()
        agg = qs.aggregate(
            valor_total=Sum("valor_nota"),
            valor_icms=Sum("valor_icms"),
            valor_pis=Sum("valor_pis"),
            valor_cofins=Sum("valor_cofins"),
            valor_ipi=Sum("valor_ipi"),
            valor_icms_st=Sum("valor_icms_st"),
        )
        for k, v in agg.items():
            if v is None:
                agg[k] = 0

        top_emitentes = (
            qs.values("emit_cnpj", "emit_nome")
            .annotate(total=Sum("valor_nota"), qtd=Count("id"))
            .order_by("-total")[:10]
        )
        top_destinatarios = (
            qs.values("dest_cnpj", "dest_nome")
            .annotate(total=Sum("valor_nota"), qtd=Count("id"))
            .order_by("-total")[:10]
        )

        itens_agg = (
            NotaFiscalItem.objects.filter(nota_fiscal__in=qs)
            .values("ncm", "descricao", "cfop")
            .annotate(total=Sum("valor_total"), qtd=Count("id"))
            .order_by("-total")[:15]
        )
        top_produtos = list(itens_agg)

        por_finalidade = list(
            qs.values("finalidade")
            .annotate(qtd=Count("id"), total=Sum("valor_nota"))
            .order_by("finalidade")
        )

        return Response({
            "total_nfs": total_nfs,
            "valores": agg,
            "top_emitentes": list(top_emitentes),
            "top_destinatarios": list(top_destinatarios),
            "top_produtos": top_produtos,
            "por_finalidade": por_finalidade,
        })


class NotaFiscalItemViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = NotaFiscalItem.objects.all()
    serializer_class = NotaFiscalItemSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["ncm", "cfop", "nota_fiscal", "produto"]
