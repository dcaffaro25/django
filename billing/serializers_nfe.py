# -*- coding: utf-8 -*-
"""Serializers para NotaFiscal, NotaFiscalItem e NFeEvento."""
from rest_framework import serializers
from .models_nfe import NotaFiscal, NotaFiscalItem, NFeEvento


class NotaFiscalItemSerializer(serializers.ModelSerializer):
    produto_nome = serializers.CharField(source="produto.name", read_only=True, allow_null=True)

    class Meta:
        model = NotaFiscalItem
        fields = [
            "id", "nota_fiscal", "numero_item",
            "codigo_produto", "ean", "descricao", "ncm", "cest", "cfop",
            "unidade", "quantidade", "valor_unitario", "valor_total",
            "produto", "produto_nome",
            "icms_origem", "icms_cst", "icms_base", "icms_aliquota", "icms_valor",
            "icms_st_base", "icms_st_valor",
            "pis_cst", "pis_base", "pis_aliquota", "pis_valor",
            "cofins_cst", "cofins_base", "cofins_aliquota", "cofins_valor",
            "ipi_cst", "ipi_valor",
            "icms_uf_dest_base", "icms_uf_dest_valor", "icms_uf_remet_valor",
            "info_adicional",
        ]


class NotaFiscalSerializer(serializers.ModelSerializer):
    itens = NotaFiscalItemSerializer(many=True, read_only=True)
    emitente_nome = serializers.SerializerMethodField()
    destinatario_nome = serializers.SerializerMethodField()

    class Meta:
        model = NotaFiscal
        fields = "__all__"

    def get_emitente_nome(self, obj):
        if obj.emitente_id:
            return obj.emitente.name
        return obj.emit_nome or None

    def get_destinatario_nome(self, obj):
        if obj.destinatario_id:
            return obj.destinatario.name
        return obj.dest_nome or None


class NotaFiscalListSerializer(serializers.ModelSerializer):
    """Versão compacta para listagem (sem itens, sem xml_original, sem JSONFields grandes)."""
    emitente_nome = serializers.SerializerMethodField()
    destinatario_nome = serializers.SerializerMethodField()

    class Meta:
        model = NotaFiscal
        exclude = ["xml_original", "totais_json", "transporte_json", "financeiro_json", "referencias_json"]

    def get_emitente_nome(self, obj):
        if obj.emitente_id:
            return obj.emitente.name
        return obj.emit_nome or None

    def get_destinatario_nome(self, obj):
        if obj.destinatario_id:
            return obj.destinatario.name
        return obj.dest_nome or None


class NFeImportResultSerializer(serializers.Serializer):
    """Resposta do endpoint de importação."""
    importadas = serializers.ListField(child=serializers.DictField())
    duplicadas = serializers.ListField(child=serializers.CharField())
    erros = serializers.ListField(child=serializers.DictField())


class NFeEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = NFeEvento
        fields = [
            "id", "nota_fiscal", "chave_nfe", "tipo_evento", "n_seq_evento",
            "data_evento", "descricao", "protocolo", "status_sefaz", "motivo_sefaz",
            "data_registro", "arquivo_origem", "company", "created_at",
        ]


class NFeEventoImportResultSerializer(serializers.Serializer):
    """Resposta do endpoint de importação de eventos e inutilizações."""
    importados = serializers.ListField(child=serializers.DictField())
    importados_inut = serializers.ListField(child=serializers.DictField())
    duplicados = serializers.ListField(child=serializers.CharField())
    erros = serializers.ListField(child=serializers.DictField())
