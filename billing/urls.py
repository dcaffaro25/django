# NORD/billing/urls.py
from django.urls import re_path, include
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

router.register('business_partner_categories', BusinessPartnerCategoryViewSet)
router.register('business_partners', BusinessPartnerViewSet)
router.register('product_service_categories', ProductServiceCategoryViewSet)
router.register('product_services', ProductServiceViewSet)
router.register('contracts', ContractViewSet)
router.register('invoices', InvoiceViewSet)
router.register('invoice_lines', InvoiceLineViewSet)

urlpatterns = [
    # NOTE: no extra 'api/' here — project urls mount this at /<tenant>/api/
    re_path(r'api/', include(router.urls)),
]
