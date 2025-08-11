# NORD/billing/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BusinessPartnerCategoryViewSet,
    BusinessPartnerViewSet,
    ProductServiceCategoryViewSet,
    ProductServiceViewSet,
    ContractViewSet,
    InvoiceViewSet,
    InvoiceLineViewSet,
)

router = DefaultRouter()
router.trailing_slash = r'/?'

router.register(r'business_partner_categories', BusinessPartnerCategoryViewSet)
router.register(r'business_partners', BusinessPartnerViewSet)
router.register(r'product_service_categories', ProductServiceCategoryViewSet)
router.register(r'product_services', ProductServiceViewSet)
router.register(r'contracts', ContractViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'invoice_lines', InvoiceLineViewSet)

urlpatterns = [
    path(r'^api/?$', include(router.urls)),
]