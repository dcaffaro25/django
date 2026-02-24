# -*- coding: utf-8 -*-
"""
Tabela de CFOP (Código Fiscal de Operações e Prestações) para vínculo com itens de NF-e
e análises por tipo de operação (venda, devolução, compra, cancelamento).

Estrutura do código (4 dígitos):
- 1º: 1,2,3 = Entrada | 5,6,7 = Saída
- 2º: 1 = operações gerais, 2 = devoluções, 3 = exportação, etc.
- 3º e 4º: detalhamento da operação

Fonte: CONFAZ/SINIEF (Ajuste SINIEF nº 3/2024). Tabela nacional, sem vínculo a tenant.
"""
from django.db import models


class CFOP(models.Model):
    """
    Código Fiscal de Operações e Prestações (tabela nacional).
    Usado para vincular NotaFiscalItem e permitir análises por grupo (venda, devolução, compra).
    """
    TIPO_OPERACAO_CHOICES = [
        ("E", "Entrada"),
        ("S", "Saída"),
    ]
    GRUPO_ANALISE_CHOICES = [
        ("venda", "Venda"),
        ("devolucao", "Devolução"),
        ("compra", "Compra"),
        ("prestacao_servico", "Prestação de serviço"),
        ("exportacao", "Exportação"),
        ("outros", "Outros"),
    ]

    codigo = models.CharField(
        "Código CFOP",
        max_length=4,
        unique=True,
        db_index=True,
        help_text="Código de 4 dígitos (ex.: 5101, 1202).",
    )
    descricao = models.CharField(
        "Descrição",
        max_length=300,
        help_text="Descrição oficial da operação conforme tabela CONFAZ.",
    )
    tipo_operacao = models.CharField(
        "Tipo operação",
        max_length=1,
        choices=TIPO_OPERACAO_CHOICES,
        db_index=True,
        help_text="E=Entrada (1xxx,2xxx,3xxx), S=Saída (5xxx,6xxx,7xxx).",
    )
    grupo_analise = models.CharField(
        "Grupo para análise",
        max_length=20,
        choices=GRUPO_ANALISE_CHOICES,
        default="outros",
        db_index=True,
        help_text="Agrupamento para relatórios: venda, devolução, compra, etc.",
    )
    ativo = models.BooleanField(
        "Ativo",
        default=True,
        help_text="Se false, código não é mais utilizado (histórico).",
    )

    class Meta:
        verbose_name = "CFOP"
        verbose_name_plural = "CFOP"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.descricao[:50]}"

    @classmethod
    def tipo_from_codigo(cls, codigo):
        """Retorna 'E' ou 'S' a partir do primeiro dígito do código."""
        if not codigo or len(str(codigo).strip()) < 1:
            return "E"
        first = str(codigo).strip()[0]
        return "S" if first in ("5", "6", "7") else "E"

    @classmethod
    def grupo_from_codigo(cls, codigo):
        """
        Estima grupo_analise pelo código quando não houver registro na tabela.
        Segundo dígito 2 = devolução; 1xxx/2xxx = compra; 5xxx/6xxx/7xxx = venda (exceto 5.2/6.2).
        """
        c = str(codigo).strip()
        if len(c) < 2:
            return "outros"
        first, second = c[0], c[1]
        if second == "2":
            return "devolucao"
        if first in ("1", "2", "3"):
            return "compra"
        if first in ("5", "6", "7"):
            return "venda"
        return "outros"
