from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine
)
from .serializers import (
    BusinessPartnerCategorySerializer, BusinessPartnerSerializer,
    ProductServiceCategorySerializer, ProductServiceSerializer,
    ContractSerializer, InvoiceSerializer, InvoiceLineSerializer
)
from multitenancy.api_utils import generic_bulk_create, generic_bulk_update, generic_bulk_delete

class BusinessPartnerCategoryViewSet(viewsets.ModelViewSet):
    queryset = BusinessPartnerCategory.objects.all()
    serializer_class = BusinessPartnerCategorySerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class BusinessPartnerViewSet(viewsets.ModelViewSet):
    queryset = BusinessPartner.objects.all()
    serializer_class = BusinessPartnerSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class ProductServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductServiceCategory.objects.all()
    serializer_class = ProductServiceCategorySerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class ProductServiceViewSet(viewsets.ModelViewSet):
    queryset = ProductService.objects.all()
    serializer_class = ProductServiceSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    serializer_class = InvoiceSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class InvoiceLineViewSet(viewsets.ModelViewSet):
    queryset = InvoiceLine.objects.all()
    serializer_class = InvoiceLineSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)

class ContractViewSet(viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    
    @action(methods=['post'], detail=False)
    def bulk_create(self, request):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request):
        return generic_bulk_delete(self, request.data)