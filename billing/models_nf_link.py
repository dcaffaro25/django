# -*- coding: utf-8 -*-
"""
M:N relação entre Transaction (accounting) e NotaFiscal (billing).

Mantida fora dos modelos contábeis para não exigir alteração no schema de
``accounting``: o link é registrado em uma tabela do app billing, com FKs nas
duas pontas. Read-only ponto-de-vista do GL: criar/aceitar/rejeitar links nunca
modifica Transaction nem JournalEntry.

Cada linha carrega:
- método de match (qual sinal disparou o vínculo)
- confiança (0..1)
- status de revisão (suggested / accepted / rejected)
- valor alocado (para casos parciais N:1)
- snapshot do amount no momento do match (para detecção posterior de drift)

A unicidade é por ``(company, transaction, nota_fiscal)`` — duplicar um par
exato é sempre erro; *múltiplos* NFs em uma Tx ou múltiplas Tx em uma NF são
permitidos via linhas distintas.
"""
from django.db import models

from multitenancy.models import TenantAwareBaseModel


class NFTransactionLink(TenantAwareBaseModel):
    """Vínculo sugerido / confirmado entre uma Transaction e uma NotaFiscal."""

    METHOD_NF_NUMBER = "nf_number"
    METHOD_DESCRIPTION_REGEX = "description_regex"
    METHOD_BANK_DESCRIPTION = "bank_description"
    METHOD_MANUAL = "manual"
    METHOD_BACKFILL = "backfill"
    METHOD_CHOICES = [
        (METHOD_NF_NUMBER, "Match por nf_number"),
        (METHOD_DESCRIPTION_REGEX, "Regex em description"),
        (METHOD_BANK_DESCRIPTION, "Regex em BankTransaction"),
        (METHOD_MANUAL, "Manual"),
        (METHOD_BACKFILL, "Backfill"),
    ]

    REVIEW_SUGGESTED = "suggested"
    REVIEW_ACCEPTED = "accepted"
    REVIEW_REJECTED = "rejected"
    REVIEW_CHOICES = [
        (REVIEW_SUGGESTED, "Sugerido"),
        (REVIEW_ACCEPTED, "Aceito"),
        (REVIEW_REJECTED, "Rejeitado"),
    ]

    transaction = models.ForeignKey(
        "accounting.Transaction",
        on_delete=models.CASCADE,
        related_name="nf_links",
        help_text="Lançamento contábil que corresponde à Nota Fiscal.",
    )
    nota_fiscal = models.ForeignKey(
        "billing.NotaFiscal",
        on_delete=models.CASCADE,
        related_name="transaction_links",
        help_text="NF vinculada à transação.",
    )

    allocated_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Valor da NF coberto por esta Tx (para casos parciais). Quando "
            "vazio o operador deve assumir que a Tx cobre integralmente a NF."
        ),
    )
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=0,
        help_text="Confiança do match (0..1). 0 = manual sem sinal.",
    )
    method = models.CharField(
        max_length=32,
        choices=METHOD_CHOICES,
        default=METHOD_NF_NUMBER,
        db_index=True,
    )
    matched_fields = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista dos campos que casaram, ex: ["nf_number","cnpj","date","amount"].',
    )
    review_status = models.CharField(
        max_length=16,
        choices=REVIEW_CHOICES,
        default=REVIEW_SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "multitenancy.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="nf_links_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    # Snapshot dos valores fonte no momento do match — usado para detectar
    # quando Tx ou NF foram alterados após a aceitação (link "rancido").
    tx_amount_snapshot = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
    )
    nf_valor_snapshot = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
    )

    class Meta:
        verbose_name = "Vínculo NF ↔ Transação"
        verbose_name_plural = "Vínculos NF ↔ Transação"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "transaction", "nota_fiscal"],
                name="billing_nflink_company_tx_nf_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "review_status"]),
            models.Index(fields=["company", "nota_fiscal", "review_status"]),
            models.Index(fields=["company", "transaction", "review_status"]),
            models.Index(fields=["company", "method"]),
        ]

    def __str__(self):
        return f"Tx#{self.transaction_id} ↔ NF#{self.nota_fiscal_id} ({self.review_status})"

    @property
    def is_stale(self):
        """True quando snapshot diverge dos valores atuais (valores mudaram pós-match)."""
        if self.tx_amount_snapshot is None or self.nf_valor_snapshot is None:
            return False
        try:
            tx_amt = self.transaction.amount
            nf_val = self.nota_fiscal.valor_nota
        except Exception:
            return False
        return tx_amt != self.tx_amount_snapshot or nf_val != self.nf_valor_snapshot
