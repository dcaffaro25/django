# -*- coding: utf-8 -*-
"""Views e endpoints para NFe: importação e CRUD + análise."""
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, TruncMonth

from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend

from .models_nfe import NotaFiscal, NotaFiscalItem, NFeEvento
from .serializers_nfe import (
    NotaFiscalSerializer,
    NotaFiscalListSerializer,
    NotaFiscalItemSerializer,
    NFeImportResultSerializer,
    NFeUnifiedImportResultSerializer,
    NFeEventoSerializer,
    NFeEventoImportResultSerializer,
)
from .services.nfe_import_service import import_many, import_nfe_xml_many
from .services.nfe_event_import_service import import_events_many
from multitenancy.mixins import ScopedQuerysetMixin

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1MB per file
MAX_FILES = settings.DATA_UPLOAD_MAX_NUMBER_FILES


class NFeImportView(APIView):
    """
    POST /api/nfe/import/ — upload de múltiplos XMLs (multipart/form-data, campo 'files').
    Interpreta cada arquivo: NFe (nota), evento (cancelamento, CCe, etc.) ou inutilização,
    e processa com o importador correto. Um único endpoint para todos os tipos.
    """
    parser_classes = [MultiPartParser]

    def post(self, request, tenant_id=None, **kwargs):
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
        result = import_nfe_xml_many(files, company)
        serializer = NFeUnifiedImportResultSerializer(result)
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

    def _apply_analise_filters(self, qs, request):
        """Aplica filtros comuns de período e CNPJ (data_inicio, data_fim, emit_cnpj, dest_cnpj)."""
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
        return qs

    @action(methods=["get"], detail=False, url_path="resumo")
    def resumo(self, request, **kwargs):
        """
        GET /api/nfe/resumo/?data_inicio=...&data_fim=...&emit_cnpj=...&dest_cnpj=...
        Retorna totais, soma por imposto, top emitentes, top produtos, distribuição por finalidade.
        """
        qs = self.get_queryset()
        qs = self._apply_analise_filters(qs, request)

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

    @action(methods=["get"], detail=False, url_path="analises")
    def analises(self, request, **kwargs):
        """
        GET /api/nfe/analises/?tipo=por_status|por_uf|evolucao|financeiro|tributos|referencias
        Filtros: data_inicio, data_fim, emit_cnpj, dest_cnpj.
        Retorna análise agregada conforme tipo.
        """
        qs = self.get_queryset()
        qs = self._apply_analise_filters(qs, request)
        tipo = (request.query_params.get("tipo") or "").strip().lower()

        if tipo == "por_status":
            rows = (
                qs.values("status_sefaz")
                .annotate(qtd=Count("id"), total=Sum("valor_nota"))
                .order_by("-total")
            )
            return Response({"tipo": "por_status", "dados": list(rows)})

        if tipo == "por_uf":
            por_emit_uf = list(
                qs.values("emit_uf")
                .annotate(qtd=Count("id"), total=Sum("valor_nota"))
                .order_by("-total")
            )
            por_dest_uf = list(
                qs.values("dest_uf")
                .annotate(qtd=Count("id"), total=Sum("valor_nota"))
                .order_by("-total")
            )
            return Response({
                "tipo": "por_uf",
                "por_emit_uf": por_emit_uf,
                "por_dest_uf": por_dest_uf,
            })

        if tipo == "evolucao":
            agrupamento = (request.query_params.get("agrupamento") or "mes").strip().lower()
            if agrupamento == "dia":
                trunc = TruncDate("data_emissao")
            else:
                trunc = TruncMonth("data_emissao")
            rows = (
                qs.annotate(periodo=trunc)
                .values("periodo")
                .annotate(
                    qtd=Count("id"),
                    valor_total=Sum("valor_nota"),
                    valor_icms=Sum("valor_icms"),
                    valor_pis=Sum("valor_pis"),
                    valor_cofins=Sum("valor_cofins"),
                )
                .order_by("periodo")
            )
            out = []
            for r in rows:
                r_copy = dict(r)
                if r_copy.get("periodo"):
                    r_copy["periodo"] = str(r_copy["periodo"])
                out.append(r_copy)
            return Response({"tipo": "evolucao", "agrupamento": agrupamento, "dados": out})

        if tipo == "financeiro":
            hoje = timezone.now().date()
            faixas = {"vencidas": Decimal("0"), "ate_30": Decimal("0"), "ate_60": Decimal("0"), "ate_90": Decimal("0"), "acima_90": Decimal("0")}
            total_duplicatas = Decimal("0")

            def parse_date(s):
                if not s:
                    return None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        return datetime.strptime(str(s)[:10], fmt).date()
                    except (ValueError, TypeError):
                        continue
                return None

            def parse_value(s):
                if s is None or s == "":
                    return Decimal("0")
                try:
                    return Decimal(str(s).replace(",", "."))
                except Exception:
                    return Decimal("0")

            for nf in qs.only("id", "financeiro_json"):
                fin = nf.financeiro_json or []
                for item in fin:
                    if item.get("tipo") != "duplicata":
                        continue
                    venc = parse_date(item.get("dVenc"))
                    val = parse_value(item.get("vDup"))
                    total_duplicatas += val
                    if venc is None:
                        faixas["vencidas"] += val
                        continue
                    delta = (venc - hoje).days
                    if delta < 0:
                        faixas["vencidas"] += val
                    elif delta <= 30:
                        faixas["ate_30"] += val
                    elif delta <= 60:
                        faixas["ate_60"] += val
                    elif delta <= 90:
                        faixas["ate_90"] += val
                    else:
                        faixas["acima_90"] += val

            return Response({
                "tipo": "financeiro",
                "total_duplicatas": str(total_duplicatas),
                "por_faixa_vencimento": {k: str(v) for k, v in faixas.items()},
            })

        if tipo == "tributos":
            agg = qs.aggregate(
                valor_nota=Sum("valor_nota"),
                valor_icms=Sum("valor_icms"),
                valor_pis=Sum("valor_pis"),
                valor_cofins=Sum("valor_cofins"),
                valor_trib_aprox=Sum("valor_trib_aprox"),
                qtd=Count("id"),
            )
            for k, v in agg.items():
                if v is None:
                    agg[k] = 0 if k == "qtd" else "0.00"
                elif k != "qtd":
                    agg[k] = str(v)
            return Response({"tipo": "tributos", "dados": agg})

        if tipo == "referencias":
            referenciadoras = qs.exclude(referencias_json=[]).exclude(referencias_json={}).count()
            com_referencias = [r for nf in qs.only("referencias_json") for r in (nf.referencias_json or [])]
            return Response({
                "tipo": "referencias",
                "nfs_referenciadoras": referenciadoras,
                "total_referencias": len(com_referencias),
            })

        return Response(
            {"detail": "tipo inválido ou ausente. Use tipo=por_status|por_uf|evolucao|financeiro|tributos|referencias"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(methods=["get"], detail=False, url_path="canceladas")
    def canceladas(self, request, **kwargs):
        """GET /api/nfe/canceladas/ — NFes canceladas (evento 110111 ou status_sefaz=101)."""
        from django.db.models import Q
        qs = self.get_queryset()
        qs = self._apply_analise_filters(qs, request)
        company = getattr(request, "tenant", None)
        chaves_evento = set()
        if company:
            chaves_evento = set(
                NFeEvento.objects.filter(company=company, tipo_evento=110111)
                .values_list("chave_nfe", flat=True)
            )
        nfs = qs.filter(Q(status_sefaz="101") | Q(chave__in=chaves_evento))
        serializer = NotaFiscalListSerializer(nfs, many=True)
        return Response({
            "total": nfs.count(),
            "nfs": serializer.data,
        })

    @action(methods=["get"], detail=False, url_path="com-cce")
    def com_cce(self, request, **kwargs):
        """GET /api/nfe/com-cce/ — NFes que possuem pelo menos uma Carta de Correção (evento 110110)."""
        qs = self.get_queryset()
        qs = self._apply_analise_filters(qs, request)
        chaves_cce = set(
            NFeEvento.objects.filter(company=request.tenant, tipo_evento=110110)
            .values_list("chave_nfe", flat=True)
        )
        nfs = qs.filter(chave__in=chaves_cce)
        serializer = NotaFiscalListSerializer(nfs, many=True)
        return Response({
            "total": nfs.count(),
            "nfs": serializer.data,
        })

    @action(methods=["get"], detail=False, url_path="manifestacao")
    def manifestacao(self, request, **kwargs):
        """GET /api/nfe/manifestacao/ — Contagem por tipo de manifestação do destinatário (210200, 210210, 210220, 210240)."""
        qs = NFeEvento.objects.filter(company=request.tenant).filter(
            tipo_evento__in=[210200, 210210, 210220, 210240]
        )
        data_inicio = request.query_params.get("data_inicio")
        data_fim = request.query_params.get("data_fim")
        if data_inicio:
            qs = qs.filter(data_evento__date__gte=data_inicio)
        if data_fim:
            qs = qs.filter(data_evento__date__lte=data_fim)
        por_tipo = list(
            qs.values("tipo_evento")
            .annotate(qtd=Count("id"))
            .order_by("tipo_evento")
        )
        return Response({
            "por_tipo": por_tipo,
            "total": sum(p["qtd"] for p in por_tipo),
        })

    @action(methods=["get"], detail=False, url_path="timeline-por-chave")
    def timeline_por_chave(self, request, **kwargs):
        """GET /api/nfe/timeline-por-chave/?chave=44digitos — Timeline de eventos pela chave da NF."""
        chave = (request.query_params.get("chave") or "").strip()
        if len(chave) != 44 or not chave.isdigit():
            return Response(
                {"detail": "Informe chave com 44 dígitos (query param chave)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company = getattr(request, "tenant", None)
        if not company:
            return Response({"detail": "Tenant não identificado."}, status=status.HTTP_400_BAD_REQUEST)
        nf = NotaFiscal.objects.filter(company=company, chave=chave).first()
        eventos = list(
            NFeEvento.objects.filter(company=company, chave_nfe=chave)
            .order_by("data_evento", "n_seq_evento")
        )
        linhas = []
        if nf:
            linhas.append({
                "tipo": "autorizacao",
                "tipo_evento": None,
                "data_evento": nf.data_autorizacao.isoformat() if nf.data_autorizacao else None,
                "protocolo": nf.protocolo,
                "status_sefaz": nf.status_sefaz,
                "motivo_sefaz": nf.motivo_sefaz,
            })
        for ev in eventos:
            linhas.append({
                "tipo": "evento",
                "tipo_evento": ev.tipo_evento,
                "n_seq_evento": ev.n_seq_evento,
                "data_evento": ev.data_evento.isoformat() if ev.data_evento else None,
                "descricao": (ev.descricao or "")[:200],
                "protocolo": ev.protocolo,
                "status_sefaz": ev.status_sefaz,
                "motivo_sefaz": ev.motivo_sefaz,
            })
        return Response({
            "chave": chave,
            "numero": nf.numero if nf else None,
            "nf_id": nf.pk if nf else None,
            "timeline": linhas,
        })

    @action(methods=["get"], detail=True, url_path="timeline")
    def timeline(self, request, pk=None, **kwargs):
        """GET /api/nfe/{id}/timeline/ — Eventos da NF (autorização + eventos NFeEvento)."""
        nf = self.get_object()
        eventos = list(
            NFeEvento.objects.filter(company=nf.company, chave_nfe=nf.chave)
            .order_by("data_evento", "n_seq_evento")
        )
        linha_autorizacao = {
            "tipo": "autorizacao",
            "tipo_evento": None,
            "data_evento": nf.data_autorizacao.isoformat() if nf.data_autorizacao else None,
            "protocolo": nf.protocolo,
            "status_sefaz": nf.status_sefaz,
            "motivo_sefaz": nf.motivo_sefaz,
        }
        linhas = [linha_autorizacao]
        for ev in eventos:
            linhas.append({
                "tipo": "evento",
                "tipo_evento": ev.tipo_evento,
                "n_seq_evento": ev.n_seq_evento,
                "data_evento": ev.data_evento.isoformat() if ev.data_evento else None,
                "descricao": (ev.descricao or "")[:200],
                "protocolo": ev.protocolo,
                "status_sefaz": ev.status_sefaz,
                "motivo_sefaz": ev.motivo_sefaz,
            })
        return Response({"chave": nf.chave, "numero": nf.numero, "timeline": linhas})


class NotaFiscalItemViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = NotaFiscalItem.objects.all()
    serializer_class = NotaFiscalItemSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["ncm", "cfop", "nota_fiscal", "produto"]


class NFeEventoViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = NFeEvento.objects.all()
    serializer_class = NFeEventoSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["chave_nfe", "tipo_evento", "nota_fiscal", "status_sefaz"]
