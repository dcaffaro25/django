from rest_framework import serializers
from .models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine,
    NFTransactionLink, InvoiceNFLink, BillingTenantConfig,
    BusinessPartnerGroup, BusinessPartnerGroupMembership,
    BusinessPartnerAlias,
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
    # Group context — read-only annotations so the frontend can render the
    # Leroy-Merlin-style "main + branches" view without a follow-up call.
    group_id = serializers.SerializerMethodField()
    group_primary_partner_id = serializers.SerializerMethodField()
    group_role = serializers.SerializerMethodField()

    class Meta:
        model = BusinessPartner
        fields = '__all__'

    def _accepted_membership(self, obj):
        for m in obj.group_memberships.all():
            if m.review_status == BusinessPartnerGroupMembership.REVIEW_ACCEPTED:
                return m
        return None

    def get_group_id(self, obj):
        m = self._accepted_membership(obj)
        return m.group_id if m else None

    def get_group_primary_partner_id(self, obj):
        m = self._accepted_membership(obj)
        return m.group.primary_partner_id if m else None

    def get_group_role(self, obj):
        m = self._accepted_membership(obj)
        return m.role if m else None

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
    # When the link was scored via a cross-root BusinessPartnerGroup
    # match (matched_fields contains 'cnpj_group'), expose the group id
    # so the review UI can open the inline group editor without a
    # follow-up roundtrip.
    cnpj_group_id = serializers.SerializerMethodField()

    def get_cnpj_group_id(self, obj):
        if 'cnpj_group' not in (obj.matched_fields or []):
            return None
        try:
            from billing.services.bp_group_service import (
                find_shared_group, resolve_bp_by_cnpj,
            )
            tx = obj.transaction
            nf = obj.nota_fiscal
            if not tx or not nf:
                return None
            bp_tx = resolve_bp_by_cnpj(tx.company, getattr(tx, 'cnpj', None))
            if bp_tx is None:
                return None
            nf_bp = nf.emitente if nf.emitente_id else nf.destinatario
            shared = find_shared_group(bp_tx, nf_bp)
            return shared.id if shared else None
        except Exception:
            return None

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
            'is_stale', 'cnpj_group_id',
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


# ============================================================
# BusinessPartnerGroup / Membership / Alias
# ============================================================

class BusinessPartnerGroupMembershipSerializer(serializers.ModelSerializer):
    """Lista de membros de um grupo, com contexto suficiente para a UI
    montar os cards de revisão sem N+1 follow-ups."""
    business_partner_name = serializers.CharField(
        source='business_partner.name', read_only=True,
    )
    business_partner_identifier = serializers.CharField(
        source='business_partner.identifier', read_only=True,
    )
    business_partner_partner_type = serializers.CharField(
        source='business_partner.partner_type', read_only=True,
    )
    group_name = serializers.CharField(source='group.name', read_only=True)
    group_primary_partner_id = serializers.IntegerField(
        source='group.primary_partner_id', read_only=True,
    )

    class Meta:
        model = BusinessPartnerGroupMembership
        fields = [
            'id', 'company', 'group', 'business_partner',
            'role', 'review_status', 'confidence', 'hit_count',
            'evidence', 'reviewed_by', 'reviewed_at',
            'business_partner_name', 'business_partner_identifier',
            'business_partner_partner_type',
            'group_name', 'group_primary_partner_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'reviewed_by', 'reviewed_at', 'hit_count', 'evidence',
        ]


class BusinessPartnerGroupSerializer(serializers.ModelSerializer):
    """Group + members embutidos, suficiente para render expansion na UI."""
    primary_partner_name = serializers.CharField(
        source='primary_partner.name', read_only=True,
    )
    primary_partner_identifier = serializers.CharField(
        source='primary_partner.identifier', read_only=True,
    )
    memberships = BusinessPartnerGroupMembershipSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()
    accepted_member_count = serializers.SerializerMethodField()

    class Meta:
        model = BusinessPartnerGroup
        fields = [
            'id', 'company', 'name', 'description', 'is_active',
            'primary_partner', 'primary_partner_name', 'primary_partner_identifier',
            'memberships', 'member_count', 'accepted_member_count',
            'created_at', 'updated_at',
        ]

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_accepted_member_count(self, obj):
        return obj.memberships.filter(
            review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
        ).count()


class BusinessPartnerAliasSerializer(serializers.ModelSerializer):
    business_partner_name = serializers.CharField(
        source='business_partner.name', read_only=True,
    )
    business_partner_identifier = serializers.CharField(
        source='business_partner.identifier', read_only=True,
    )

    class Meta:
        model = BusinessPartnerAlias
        fields = [
            'id', 'company', 'business_partner', 'kind', 'alias_identifier',
            'review_status', 'source', 'confidence', 'hit_count',
            'last_used_at', 'evidence', 'reviewed_by', 'reviewed_at',
            'business_partner_name', 'business_partner_identifier',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'reviewed_by', 'reviewed_at', 'hit_count', 'evidence',
            'last_used_at',
        ]


# =====================================================================
# ProductServiceGroup serializers — mirror BusinessPartnerGroup* on
# the product side.
# =====================================================================


class ProductServiceGroupMembershipSerializer(serializers.ModelSerializer):
    """One membership row with enough product context for the review UI.

    Mirrors ``BusinessPartnerGroupMembershipSerializer`` — flat fields
    inlined so the suggestion cards never have to follow up with N+1
    requests for product name / code.
    """
    product_service_name = serializers.CharField(
        source='product_service.name', read_only=True,
    )
    product_service_code = serializers.CharField(
        source='product_service.code', read_only=True,
    )
    product_service_item_type = serializers.CharField(
        source='product_service.item_type', read_only=True,
    )
    group_name = serializers.CharField(source='group.name', read_only=True)
    group_primary_product_id = serializers.IntegerField(
        source='group.primary_product_id', read_only=True,
    )

    class Meta:
        from billing.models_product_groups import ProductServiceGroupMembership
        model = ProductServiceGroupMembership
        fields = [
            'id', 'company', 'group', 'product_service',
            'role', 'review_status', 'confidence', 'hit_count',
            'evidence', 'reviewed_by', 'reviewed_at',
            'product_service_name', 'product_service_code',
            'product_service_item_type',
            'group_name', 'group_primary_product_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'reviewed_by', 'reviewed_at', 'hit_count', 'evidence',
        ]


class ProductServiceGroupSerializer(serializers.ModelSerializer):
    """Group + memberships embedded, enough to render expansion on the UI."""
    primary_product_name = serializers.CharField(
        source='primary_product.name', read_only=True,
    )
    primary_product_code = serializers.CharField(
        source='primary_product.code', read_only=True,
    )
    memberships = ProductServiceGroupMembershipSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()
    accepted_member_count = serializers.SerializerMethodField()

    class Meta:
        from billing.models_product_groups import ProductServiceGroup
        model = ProductServiceGroup
        fields = [
            'id', 'company', 'name', 'description', 'is_active',
            'primary_product', 'primary_product_name', 'primary_product_code',
            'memberships', 'member_count', 'accepted_member_count',
            'created_at', 'updated_at',
        ]

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_accepted_member_count(self, obj):
        from billing.models_product_groups import ProductServiceGroupMembership
        return obj.memberships.filter(
            review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
        ).count()


class ProductServiceAliasSerializer(serializers.ModelSerializer):
    product_service_name = serializers.CharField(
        source='product_service.name', read_only=True,
    )
    product_service_code = serializers.CharField(
        source='product_service.code', read_only=True,
    )

    class Meta:
        from billing.models_product_groups import ProductServiceAlias
        model = ProductServiceAlias
        fields = [
            'id', 'company', 'product_service', 'kind', 'alias_identifier',
            'review_status', 'source', 'confidence', 'hit_count',
            'last_used_at', 'evidence', 'reviewed_by', 'reviewed_at',
            'product_service_name', 'product_service_code',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'reviewed_by', 'reviewed_at', 'hit_count', 'evidence',
            'last_used_at',
        ]
