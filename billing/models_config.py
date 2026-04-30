# -*- coding: utf-8 -*-
"""
Per-tenant billing configuration: feature flags + posting-side defaults.
Singleton-per-tenant via UniqueConstraint on company.
"""
from decimal import Decimal

from django.db import models

from multitenancy.models import TenantAwareBaseModel


class BillingTenantConfig(TenantAwareBaseModel):
    """
    Singleton per-tenant. Read via:
        BillingTenantConfig.objects.filter(company=tenant).first()
    or the helper ``get_or_default(tenant)`` that returns a transient
    in-memory default when no row exists.
    """

    # ===== Feature flags =====
    auto_create_invoice_from_nf = models.BooleanField(
        default=False,
        help_text=(
            "Ao importar uma NF (saída, finalidade=normal) tenta casar com "
            "uma Invoice existente; se não houver match, cria uma Invoice."
        ),
    )
    auto_create_invoice_for_finalidades = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Quais finalidades disparam auto-criação. Default vazio = apenas "
            "1=Normal. Lista de inteiros como [1,2]."
        ),
    )
    auto_create_invoice_for_tipos = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Quais tipo_operacao disparam auto-criação. Default vazio = apenas "
            "1=Saída. Lista de inteiros como [0,1]."
        ),
    )

    auto_link_nf_to_transactions = models.BooleanField(
        default=True,
        help_text=(
            "Quando true, o NF importer chama nf_link_service para sugerir "
            "links com Transactions existentes."
        ),
    )
    auto_accept_link_above = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        default=Decimal("1.001"),
        help_text=(
            "Confiança a partir da qual o link é aceito automaticamente "
            "(sem revisão humana). Default 1.001 = nunca aceitar sozinho."
        ),
    )
    link_date_window_days = models.SmallIntegerField(
        default=7,
        help_text="Tolerância em dias entre Transaction.date e NotaFiscal.data_emissao no matching.",
    )
    link_amount_tolerance_pct = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.01"),
        help_text="Tolerância proporcional para casamento de valor (0.01 = 1%).",
    )

    # ===== Posting defaults (futuro Phase 4) =====
    default_receivable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="A/R default — usado quando BusinessPartner.receivable_account está vazio.",
    )
    default_payable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="A/P default — usado quando BusinessPartner.payable_account está vazio.",
    )

    class Meta:
        verbose_name = "Configuração de Faturamento"
        verbose_name_plural = "Configurações de Faturamento"
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                name="billing_tenantconfig_company_uniq",
            ),
        ]

    def __str__(self):
        return f"BillingTenantConfig({self.company_id})"

    @classmethod
    def get_or_default(cls, company):
        """Return persisted config for tenant, or a transient default instance."""
        cfg = cls.objects.filter(company=company).first()
        if cfg is not None:
            return cfg
        # Transient (not saved): callers can read fields with default values.
        return cls(company=company)

    def allowed_finalidades(self):
        """Resolve auto_create_invoice_for_finalidades to a set of int values."""
        raw = self.auto_create_invoice_for_finalidades or []
        if not raw:
            return {1}
        try:
            return {int(x) for x in raw}
        except (TypeError, ValueError):
            return {1}

    def allowed_tipos_operacao(self):
        raw = self.auto_create_invoice_for_tipos or []
        if not raw:
            return {1}
        try:
            return {int(x) for x in raw}
        except (TypeError, ValueError):
            return {1}
