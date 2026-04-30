from rest_framework import serializers
from .models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine,
    NFTransactionLink, InvoiceNFLink, BillingTenantConfig,
)

from multitenancy.serializers import FlexibleRelatedField, CompanySerializer


class BusinessPartnerCategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(source='parent.id', read_only=True)
    level = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    path_ids = serializers.SerializerMethodField()
    
    company = FlexibleRelatedField(
        serializer_class=CompanySerializer,
        unique_field='name'
    )
    
    class Meta:
        model = BusinessPartnerCategory
        fields = '__all__'
        
    def get_level(self, obj):
        """Calculate the level of the entity in the tree."""
        level = 0
        while obj.parent is not None:
            level += 1
            obj = obj.parent
        return level

    def get_path(self, obj):
        """Use the get_path method from the Entity model."""
        return obj.get_path()
    
    def get_path_ids(self, obj):
        """Retrieve the path IDs using the Entity's get_path method."""
        return obj.get_path_ids()

class BusinessPartnerSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=BusinessPartnerCategory.objects.all(), allow_null=True)

    class Meta:
        model = BusinessPartner
        fields = '__all__'

class ProductServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductServiceCategory
        fields = '__all__'

class ProductServiceSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=ProductServiceCategory.objects.all(), allow_null=True)

    class Meta:
        model = ProductService
        fields = '__all__'

class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = '__all__'


class InvoiceLineWithContextSerializer(serializers.ModelSerializer):
    """Adds invoice + product names so cross-link panels (e.g. 'show me
    every invoice line for this product') can render rows without N+1
    follow-up requests."""
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    invoice_date = serializers.DateField(source='invoice.invoice_date', read_only=True)
    invoice_status = serializers.CharField(source='invoice.status', read_only=True)
    invoice_partner = serializers.CharField(source='invoice.partner.name', read_only=True)
    product_service_name = serializers.CharField(source='product_service.name', read_only=True, allow_null=True)
    product_service_code = serializers.CharField(source='product_service.code', read_only=True, allow_null=True)

    class Meta:
        model = InvoiceLine
        fields = [
            'id', 'invoice', 'invoice_number', 'invoice_date', 'invoice_status', 'invoice_partner',
            'product_service', 'product_service_name', 'product_service_code',
            'description', 'quantity', 'unit_price', 'total_price', 'tax_amount',
        ]

class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'


class InvoiceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the list endpoint — excludes ``lines`` so
    rendering 500+ invoices doesn't trigger an N+1 join chain.
    Used by InvoiceViewSet.list()."""
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    partner_identifier = serializers.CharField(source='partner.identifier', read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'company', 'partner', 'partner_name', 'partner_identifier',
            'contract', 'erp_id', 'invoice_type', 'invoice_number',
            'invoice_date', 'due_date', 'status', 'fiscal_status',
            'has_pending_corrections', 'currency',
            'total_amount', 'tax_amount', 'discount_amount',
            'description',
            'critics_count', 'critics_count_by_severity',
            'created_at', 'updated_at',
        ]

class ContractSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        # Convert empty strings to None for specific fields
        for field in ['end_date', 'base_index_date']:
            if data.get(field) == "":
                data[field] = None
        return super().to_internal_value(data)
    
    class Meta:
        model = Contract
        fields = '__all__'
        
        
#MINI

class BusinessPartnerCategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPartnerCategory
        fields = ['id', 'name']

class BusinessPartnerMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessPartner
        fields = ['id', 'name', 'partner_type']
        
class ProductServiceCategoryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductServiceCategory
        fields = ['id', 'name']
        
class ProductServiceMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductService
        fields = ['id', 'name', 'item_type']
        
class InvoiceMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'invoice_number', 'invoice_date', 'total_amount',
                  'status', 'fiscal_status', 'has_pending_corrections']

class ContractMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'contract_number', 'start_date', 'base_value']


# ============================================================
# NF ↔ Tx link, Invoice ↔ NF link, BillingTenantConfig
# ============================================================

class NFTransactionLinkSerializer(serializers.ModelSerializer):
    """Includes denormalized tx + nf snippets so the review UI doesn't
    have to make N+1 follow-up requests."""
    transaction_amount = serializers.DecimalField(
        source='transaction.amount', max_digits=18, decimal_places=2,
        read_only=True, allow_null=True,
    )
    transaction_date = serializers.DateField(source='transaction.date', read_only=True)
    transaction_description = serializers.CharField(
        source='transaction.description', read_only=True, allow_null=True,
    )
    transaction_nf_number = serializers.CharField(
        source='transaction.nf_number', read_only=True, allow_null=True,
    )
    transaction_cnpj = serializers.CharField(
        source='transaction.cnpj', read_only=True, allow_null=True,
    )
    nf_numero = serializers.IntegerField(source='nota_fiscal.numero', read_only=True)
    nf_chave = serializers.CharField(source='nota_fiscal.chave', read_only=True)
    nf_data_emissao = serializers.DateTimeField(source='nota_fiscal.data_emissao', read_only=True)
    nf_valor_nota = serializers.DecimalField(
        source='nota_fiscal.valor_nota', max_digits=15, decimal_places=2, read_only=True,
    )
    nf_emit_nome = serializers.CharField(source='nota_fiscal.emit_nome', read_only=True)
    nf_emit_cnpj = serializers.CharField(source='nota_fiscal.emit_cnpj', read_only=True)
    nf_dest_nome = serializers.CharField(source='nota_fiscal.dest_nome', read_only=True)
    nf_dest_cnpj = serializers.CharField(source='nota_fiscal.dest_cnpj', read_only=True)
    is_stale = serializers.BooleanField(read_only=True)

    class Meta:
        model = NFTransactionLink
        fields = [
            'id', 'company', 'transaction', 'nota_fiscal',
            'allocated_amount', 'confidence', 'method', 'matched_fields',
            'review_status', 'reviewed_by', 'reviewed_at', 'notes',
            'tx_amount_snapshot', 'nf_valor_snapshot',
            'transaction_amount', 'transaction_date', 'transaction_description',
            'transaction_nf_number', 'transaction_cnpj',
            'nf_numero', 'nf_chave', 'nf_data_emissao', 'nf_valor_nota',
            'nf_emit_nome', 'nf_emit_cnpj', 'nf_dest_nome', 'nf_dest_cnpj',
            'is_stale',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['reviewed_by', 'reviewed_at']


class InvoiceNFLinkSerializer(serializers.ModelSerializer):
    nf_numero = serializers.IntegerField(source='nota_fiscal.numero', read_only=True)
    nf_chave = serializers.CharField(source='nota_fiscal.chave', read_only=True)
    nf_data_emissao = serializers.DateTimeField(source='nota_fiscal.data_emissao', read_only=True)
    nf_valor_nota = serializers.DecimalField(
        source='nota_fiscal.valor_nota', max_digits=15, decimal_places=2, read_only=True,
    )
    nf_finalidade = serializers.IntegerField(source='nota_fiscal.finalidade', read_only=True)
    nf_status_sefaz = serializers.CharField(source='nota_fiscal.status_sefaz', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    invoice_date = serializers.DateField(source='invoice.invoice_date', read_only=True)
    invoice_total_amount = serializers.DecimalField(
        source='invoice.total_amount', max_digits=12, decimal_places=2, read_only=True,
    )

    class Meta:
        model = InvoiceNFLink
        fields = [
            'id', 'company', 'invoice', 'nota_fiscal',
            'relation_type', 'allocated_amount', 'notes',
            'nf_numero', 'nf_chave', 'nf_data_emissao', 'nf_valor_nota',
            'nf_finalidade', 'nf_status_sefaz',
            'invoice_number', 'invoice_date', 'invoice_total_amount',
            'created_at', 'updated_at',
        ]


class BillingTenantConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingTenantConfig
        fields = '__all__'
        read_only_fields = ['company']


# Re-export an enriched Invoice serializer that includes attachments — used by
# the detail page. We avoid changing the existing InvoiceSerializer's shape so
# bulk import flows aren't broken; new code can opt into this one explicitly.
class InvoiceDetailSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    nf_attachments = InvoiceNFLinkSerializer(many=True, read_only=True)
    partner_name = serializers.CharField(source='partner.name', read_only=True)
    partner_identifier = serializers.CharField(source='partner.identifier', read_only=True)
    contract_number = serializers.CharField(source='contract.contract_number', read_only=True, allow_null=True)

    class Meta:
        model = Invoice
        fields = '__all__'
