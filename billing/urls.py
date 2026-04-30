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
    NFTransactionLinkViewSet,
    InvoiceNFLinkViewSet,
    BillingTenantConfigViewSet,
    BusinessPartnerGroupViewSet,
    BusinessPartnerGroupMembershipViewSet,
    BusinessPartnerAliasViewSet,
)
from .views_nfe import (
    NFeImportView,
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
router.register('nf-transaction-links', NFTransactionLinkViewSet)
router.register('invoice-nf-links', InvoiceNFLinkViewSet)
router.register('billing-config', BillingTenantConfigViewSet)
router.register('business-partner-groups', BusinessPartnerGroupViewSet)
router.register('business-partner-group-memberships', BusinessPartnerGroupMembershipViewSet)
router.register('business-partner-aliases', BusinessPartnerAliasViewSet)

urlpatterns = [
    re_path(r'api/nfe/import/?$', NFeImportView.as_view(), name='nfe-import'),
    re_path(r'api/nfe/eventos/import/?$', NFeImportView.as_view(), name='nfe-eventos-import'),  # alias: mesmo endpoint
    re_path(r'api/', include(router.urls)),
]
