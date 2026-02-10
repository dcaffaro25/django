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
from .views_nfe import (
    NFeImportView,
    NFeEventoImportView,
    NotaFiscalViewSet,
    NotaFiscalItemViewSet,
    NFeEventoViewSet,
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
router.register('nfe', NotaFiscalViewSet)
router.register('nfe-itens', NotaFiscalItemViewSet)
router.register('nfe-eventos', NFeEventoViewSet)

urlpatterns = [
    re_path(r'api/nfe/import/?$', NFeImportView.as_view(), name='nfe-import'),
    re_path(r'api/nfe/eventos/import/?$', NFeEventoImportView.as_view(), name='nfe-eventos-import'),
    re_path(r'api/', include(router.urls)),
]
