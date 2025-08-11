from rest_framework import serializers
from .models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine
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

class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'

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
        fields = ['id', 'invoice_number', 'invoice_date', 'total_amount']
        
class ContractMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'contract_number', 'start_date', 'base_value']
