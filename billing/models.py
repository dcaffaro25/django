from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from multitenancy.models import BaseModel, TenantAwareBaseModel
from core.models import FinancialIndex, IndexQuote, FinancialIndexQuoteForecast
from django.utils import timezone

class BusinessPartnerCategory(TenantAwareBaseModel, MPTTModel):
    name = models.CharField(max_length=100)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'erp_id']),
        ]

    def __str__(self):
        return self.name
    
    def get_path(self):
        """Return the full path of this entity as a string."""
        ancestors = [self.name]
        parent = self.parent
        while parent is not None:
            ancestors.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(ancestors)
    
    def get_path_ids(self):
        """Returns the list of IDs representing the full path to this entity."""
        path = []
        current = self
        while current:
            path.insert(0, current.id)  # Prepend the current entity ID
            current = current.parent
        return path
    
    class MPTTMeta:
        order_insertion_by = ['name'] 

class BusinessPartner(TenantAwareBaseModel):
    PARTNER_TYPES = [('client', 'Client'), ('vendor', 'Vendor'), ('both', 'Both')]

    name = models.CharField(max_length=255)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    partner_type = models.CharField(max_length=10, choices=PARTNER_TYPES)
    category = TreeForeignKey(BusinessPartnerCategory, null=True, blank=True, on_delete=models.SET_NULL)
    identifier = models.CharField(max_length=50)  # CPF/CNPJ; unique per company (see Meta)
    cnpj_root = models.CharField(
        max_length=8,
        blank=True,
        db_index=True,
        help_text=(
            "Primeiros 8 dígitos do CNPJ — a 'raiz' que une matriz e "
            "filiais de uma mesma pessoa jurídica. Auto-populado pelo "
            "save() quando identifier tem 14 dígitos."
        ),
    )
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    zipcode = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Brazil')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    payment_terms = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    # Account mappings used when posting Invoices/NFs to the GL. When blank,
    # caller falls back to BillingTenantConfig.default_{receivable,payable}_account.
    receivable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Conta A/R deste cliente (vendas).",
    )
    payable_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Conta A/P deste fornecedor (compras).",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'identifier'],
                name='billing_bp_company_identifier_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'erp_id']),
            models.Index(fields=['company', 'cnpj_root'], name='bp_company_cnpjroot_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.partner_type})"

    def save(self, *args, **kwargs):
        # Auto-populate cnpj_root from identifier whenever identifier
        # changes. Ignores non-CNPJ identifiers (CPF, foreign IDs).
        if self.identifier:
            digits = "".join(ch for ch in self.identifier if ch.isdigit())
            if len(digits) == 14:
                self.cnpj_root = digits[:8]
            else:
                self.cnpj_root = ""
        super().save(*args, **kwargs)

class ProductServiceCategory(TenantAwareBaseModel, MPTTModel):
    name = models.CharField(max_length=100)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'erp_id']),
        ]

    class MPTTMeta:
        order_insertion_by = ['name']

    def __str__(self):
        return self.name
    
class ProductService(TenantAwareBaseModel):
    TYPES = [('product', 'Product'), ('service', 'Service')]

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, db_index=True)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    category = TreeForeignKey(ProductServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    item_type = models.CharField(max_length=10, choices=TYPES)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    tax_code = models.CharField(max_length=50, blank=True)
    track_inventory = models.BooleanField(default=False)
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    # Account mappings for inventory reporting (products only; fallback to TenantCostingConfig when blank)
    inventory_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Inventory (balance sheet) account.",
    )
    cogs_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="COGS (income statement) account.",
    )
    adjustment_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Inventory revaluation / adjustment account.",
    )
    revenue_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Sales revenue account.",
    )
    purchase_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Purchase / goods receipt account.",
    )
    discount_given_account = models.ForeignKey(
        "accounting.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Discount given on sales account.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'code'],
                name='billing_ps_company_code_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'erp_id']),
        ]

    def __str__(self):
        return f"{self.name} ({self.item_type})"

class Contract(models.Model):
    company = models.ForeignKey('multitenancy.Company', on_delete=models.CASCADE)
    partner = models.ForeignKey('BusinessPartner', on_delete=models.CASCADE)
    contract_number = models.CharField(max_length=50, unique=True)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)

    recurrence_rule = models.TextField(
        blank=True,
        help_text="RRULE string for recurrence, e.g., FREQ=MONTHLY;INTERVAL=1"
    )

    base_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    base_index_date = models.DateField(
        null=True, blank=True,
        help_text="Start date to reference for index adjustment"
    )
    adjustment_index = models.ForeignKey(
        FinancialIndex, on_delete=models.SET_NULL,
        null=True, blank=True, help_text="Economic index used for adjustments"
    )
    adjustment_frequency = models.TextField(
        blank=True,
        help_text="RRULE string for adjustment recurrence"
    )
    adjustment_cap = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum adjustment percentage per period (e.g., 10.00 = 10%)"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'erp_id']),
        ]

    def __str__(self):
        return f"Contract {self.contract_number} with {self.partner.name}"
    
    
    
class Invoice(TenantAwareBaseModel):
    INVOICE_TYPES = [('sale', 'Sale'), ('purchase', 'Purchase')]
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('issued', 'Issued'),
        ('partially_paid', 'Partially Paid'), ('paid', 'Paid'),
        ('canceled', 'Canceled')
    ]

    # Two-axis lifecycle: payment ``status`` (operacional) +
    # ``fiscal_status`` (derivado das NFs vinculadas).
    FISCAL_STATUS_CHOICES = [
        ('pending_nf', 'Pendente de NF'),
        ('invoiced', 'Faturada (NF emitida)'),
        ('partially_returned', 'Devolvida parcialmente'),
        ('fully_returned', 'Devolvida'),
        ('fiscally_cancelled', 'NF cancelada'),
        ('mixed', 'Misto (múltiplas NFs com estados diferentes)'),
    ]

    partner = models.ForeignKey(BusinessPartner, on_delete=models.CASCADE)
    contract = models.ForeignKey(
        'Contract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='invoices',
        help_text='Contrato-mãe que originou esta fatura (recorrência).',
    )
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    invoice_type = models.CharField(max_length=10, choices=INVOICE_TYPES)
    invoice_number = models.CharField(max_length=50)
    invoice_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    recurrence_rule = models.TextField(blank=True, help_text="RRULE string for recurrence, e.g., FREQ=MONTHLY;INTERVAL=1")
    recurrence_start_date = models.DateField(null=True, blank=True)
    recurrence_end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)

    # Eixo fiscal — projeção do estado das NFs vinculadas. Não é fonte de
    # verdade: é cache. Recalculado por ``fiscal_status_service`` em hooks
    # explícitos (NF importada, evento, link aceito). Nunca derivar GL daqui.
    fiscal_status = models.CharField(
        max_length=24,
        choices=FISCAL_STATUS_CHOICES,
        default='pending_nf',
        db_index=True,
    )
    fiscal_status_computed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que o cache de fiscal_status foi recalculado.",
    )
    has_pending_corrections = models.BooleanField(
        default=False,
        help_text="True quando alguma NF vinculada teve uma CCe desde o último review.",
    )

    # Denormalized critics count — refreshed by fiscal_status_service.refresh()
    # so list endpoints can filter / sort by anomaly severity without paying
    # per-row computation cost. Excludes acknowledged critics.
    critics_count = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Número de críticas não-aceitas atualmente registradas para esta fatura.",
    )
    critics_count_by_severity = models.JSONField(
        default=dict,
        blank=True,
        help_text='Contagens por severidade: {"error": N, "warning": M, "info": K}.',
    )

    notas_fiscais = models.ManyToManyField(
        'billing.NotaFiscal',
        through='billing.InvoiceNFLink',
        through_fields=('invoice', 'nota_fiscal'),
        related_name='invoices',
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=['company', 'erp_id']),
            models.Index(fields=['company', 'fiscal_status']),
            models.Index(fields=['company', 'status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.partner.name}"

    def update_totals(self):
        self.total_amount = sum(line.total_price for line in self.lines.all())
        self.tax_amount = sum(line.tax_amount for line in self.lines.all())
        self.save(update_fields=['total_amount', 'tax_amount'])


class InvoiceNFLink(TenantAwareBaseModel):
    """
    Through-model do M:N Invoice ↔ NotaFiscal.
    Carrega o tipo de relação (normal / devolução / complementar) e o valor
    coberto, permitindo que uma Invoice satisfaça N NFs e vice-versa.
    """
    REL_NORMAL = 'normal'
    REL_DEVOLUCAO = 'devolucao'
    REL_COMPLEMENTAR = 'complementar'
    REL_AJUSTE = 'ajuste'
    REL_CHOICES = [
        (REL_NORMAL, 'Normal'),
        (REL_DEVOLUCAO, 'Devolução'),
        (REL_COMPLEMENTAR, 'Complementar'),
        (REL_AJUSTE, 'Ajuste'),
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='nf_attachments')
    nota_fiscal = models.ForeignKey(
        'billing.NotaFiscal',
        on_delete=models.CASCADE,
        related_name='invoice_attachments',
    )
    relation_type = models.CharField(
        max_length=16,
        choices=REL_CHOICES,
        default=REL_NORMAL,
        db_index=True,
    )
    allocated_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Valor da NF coberto por esta Invoice (para casos parciais).',
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Vínculo Invoice ↔ NF'
        verbose_name_plural = 'Vínculos Invoice ↔ NF'
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'invoice', 'nota_fiscal'],
                name='billing_invnflink_company_inv_nf_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['company', 'invoice']),
            models.Index(fields=['company', 'nota_fiscal']),
            models.Index(fields=['company', 'relation_type']),
        ]

    def __str__(self):
        return f"Invoice#{self.invoice_id} ↔ NF#{self.nota_fiscal_id} ({self.relation_type})"
    
class InvoiceLine(TenantAwareBaseModel):
    invoice = models.ForeignKey(Invoice, related_name='lines', on_delete=models.CASCADE)
    product_service = models.ForeignKey(ProductService, on_delete=models.CASCADE)
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'erp_id']),
        ]

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        if self.invoice:
            self.invoice.update_totals()
            
    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        if invoice:
            invoice.update_totals()
            
    def __str__(self):
        return f"{self.product_service.name} - {self.quantity} x {self.unit_price}"


# Import CFOP (tabela nacional) e modelos NFe
from .models_cfop import CFOP  # noqa: E402, F401
from .models_nfe import (  # noqa: E402
    NotaFiscal,
    NotaFiscalItem,
    NotaFiscalReferencia,
    NFeEvento,
    NFeInutilizacao,
)
from .models_nf_link import NFTransactionLink  # noqa: E402, F401
from .models_config import BillingTenantConfig  # noqa: E402, F401
from .models_critics import CriticAcknowledgement  # noqa: E402, F401
from .models_groups import (  # noqa: E402, F401
    BusinessPartnerGroup,
    BusinessPartnerGroupMembership,
    BusinessPartnerAlias,
)