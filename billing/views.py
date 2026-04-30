from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    BusinessPartnerCategory, BusinessPartner,
    ProductServiceCategory, ProductService,
    Contract, Invoice, InvoiceLine,
    NFTransactionLink, InvoiceNFLink, BillingTenantConfig,
    NotaFiscal,
)
from .serializers import (
    BusinessPartnerCategorySerializer, BusinessPartnerSerializer,
    ProductServiceCategorySerializer, ProductServiceSerializer,
    ContractSerializer, InvoiceSerializer, InvoiceLineSerializer,
    NFTransactionLinkSerializer, InvoiceNFLinkSerializer,
    BillingTenantConfigSerializer, InvoiceDetailSerializer,
    InvoiceListSerializer,
)
from multitenancy.mixins import ScopedQuerysetMixin
from multitenancy.api_utils import generic_bulk_create, generic_bulk_update, generic_bulk_delete

class BusinessPartnerCategoryViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = BusinessPartnerCategory.objects.all()
    serializer_class = BusinessPartnerCategorySerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

class BusinessPartnerViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = BusinessPartner.objects.all()
    serializer_class = BusinessPartnerSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

class ProductServiceCategoryViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ProductServiceCategory.objects.all()
    serializer_class = ProductServiceCategorySerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

class ProductServiceViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = ProductService.objects.all()
    serializer_class = ProductServiceSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

class InvoiceViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Invoice.objects.all().select_related('partner', 'contract', 'currency')
    serializer_class = InvoiceSerializer

    def get_serializer_class(self):
        # Detail endpoint returns the enriched payload (lines + nf_attachments).
        # List endpoint uses the lightweight serializer (no lines) so 500+
        # rows don't trigger an N+1 line-fetch chain.
        if self.action in ('retrieve',):
            return InvoiceDetailSerializer
        if self.action in ('list',):
            return InvoiceListSerializer
        return InvoiceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        # Optional filters used by the list page.
        fiscal = params.get('fiscal_status')
        if fiscal:
            qs = qs.filter(fiscal_status=fiscal)
        status_v = params.get('status')
        if status_v:
            qs = qs.filter(status=status_v)
        partner_id = params.get('partner')
        if partner_id:
            try:
                qs = qs.filter(partner_id=int(partner_id))
            except (TypeError, ValueError):
                pass
        date_from = params.get('date_from')
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        date_to = params.get('date_to')
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        return qs

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

    @action(methods=['post'], detail=True, url_path='attach-nf')
    def attach_nf(self, request, pk=None, **kwargs):
        """Attach an existing NotaFiscal to this Invoice via InvoiceNFLink."""
        invoice = self.get_object()
        nf_id = request.data.get('nota_fiscal')
        if not nf_id:
            return Response({'detail': 'nota_fiscal é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            nf = NotaFiscal.objects.get(company=invoice.company, pk=nf_id)
        except NotaFiscal.DoesNotExist:
            return Response({'detail': 'NF não encontrada neste tenant.'}, status=status.HTTP_404_NOT_FOUND)
        from billing.services.nf_invoice_sync import attach_invoice_to_nf
        link, created = attach_invoice_to_nf(
            invoice, nf,
            relation_type=request.data.get('relation_type'),
            allocated_amount=request.data.get('allocated_amount'),
            notes=request.data.get('notes', ''),
        )
        return Response(
            InvoiceNFLinkSerializer(link).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(methods=['post'], detail=True, url_path='refresh-fiscal-status')
    def refresh_fiscal_status_action(self, request, pk=None, **kwargs):
        invoice = self.get_object()
        from billing.services.fiscal_status_service import refresh
        refresh(invoice, persist=True)
        invoice.refresh_from_db()
        return Response(InvoiceDetailSerializer(invoice).data)

class InvoiceLineViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = InvoiceLine.objects.all()
    serializer_class = InvoiceLineSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)

class ContractViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer

    @action(methods=['post'], detail=False)
    def bulk_create(self, request, **kwargs):
        return generic_bulk_create(self, request.data)

    @action(methods=['put'], detail=False)
    def bulk_update(self, request, **kwargs):
        return generic_bulk_update(self, request.data)

    @action(methods=['delete'], detail=False)
    def bulk_delete(self, request, **kwargs):
        return generic_bulk_delete(self, request.data)


class NFTransactionLinkViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD on NF↔Tx links + custom actions for accept/reject/scan."""
    queryset = NFTransactionLink.objects.all().select_related(
        'transaction', 'nota_fiscal', 'reviewed_by',
    )
    serializer_class = NFTransactionLinkSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        rs = params.get('review_status')
        if rs:
            qs = qs.filter(review_status=rs)
        nf_id = params.get('nota_fiscal')
        if nf_id:
            try:
                qs = qs.filter(nota_fiscal_id=int(nf_id))
            except (TypeError, ValueError):
                pass
        tx_id = params.get('transaction')
        if tx_id:
            try:
                qs = qs.filter(transaction_id=int(tx_id))
            except (TypeError, ValueError):
                pass
        method = params.get('method')
        if method:
            qs = qs.filter(method=method)
        min_conf = params.get('min_confidence')
        if min_conf:
            try:
                qs = qs.filter(confidence__gte=Decimal(min_conf))
            except Exception:
                pass
        ordering = params.get('ordering') or '-confidence'
        return qs.order_by(ordering)

    @action(methods=['post'], detail=True, url_path='accept')
    def accept(self, request, pk=None, **kwargs):
        link = self.get_object()
        from billing.services.nf_link_service import accept_link
        accept_link(link, user=request.user, notes=request.data.get('notes', ''))
        link.refresh_from_db()
        return Response(NFTransactionLinkSerializer(link).data)

    @action(methods=['post'], detail=True, url_path='reject')
    def reject(self, request, pk=None, **kwargs):
        link = self.get_object()
        from billing.services.nf_link_service import reject_link
        reject_link(link, user=request.user, notes=request.data.get('notes', ''))
        link.refresh_from_db()
        return Response(NFTransactionLinkSerializer(link).data)

    @action(methods=['post'], detail=False, url_path='scan')
    def scan(self, request, **kwargs):
        """
        Run a fresh matching pass for the current tenant. Body:
          { transaction_ids?, nota_fiscal_ids?, date_window_days?,
            amount_tolerance?, min_confidence?, dry_run? }
        Returns:
          { candidates: int, persisted: {...counters}, dry_run: bool }
        """
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)

        from billing.services.nf_link_service import find_candidates, persist_links
        body = request.data or {}
        kwargs2 = {}
        if 'transaction_ids' in body:
            kwargs2['transaction_ids'] = body['transaction_ids']
        if 'nota_fiscal_ids' in body:
            kwargs2['nota_fiscal_ids'] = body['nota_fiscal_ids']
        if 'date_window_days' in body:
            kwargs2['date_window_days'] = int(body['date_window_days'])
        if 'amount_tolerance' in body:
            kwargs2['amount_tolerance'] = Decimal(str(body['amount_tolerance']))
        if 'min_confidence' in body:
            kwargs2['min_confidence'] = Decimal(str(body['min_confidence']))
        if 'limit' in body:
            kwargs2['limit'] = int(body['limit'])

        matches = find_candidates(tenant, **kwargs2)
        dry_run = bool(body.get('dry_run', False))
        counters = persist_links(tenant, matches, dry_run=dry_run)
        return Response({
            'candidates': len(matches),
            'persisted': counters,
            'dry_run': dry_run,
        })

    @action(methods=['post'], detail=False, url_path='accept-all-above')
    def accept_all_above(self, request, **kwargs):
        """
        Bulk-accept every ``suggested`` link with confidence ≥ threshold for
        the current tenant. Body: { confidence: float }.
        """
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)
        threshold = request.data.get('confidence')
        if threshold is None:
            return Response({'detail': 'confidence é obrigatório.'}, status=400)
        try:
            threshold = Decimal(str(threshold))
        except Exception:
            return Response({'detail': 'confidence inválido.'}, status=400)

        from django.utils import timezone
        qs = NFTransactionLink.objects.filter(
            company=tenant,
            review_status=NFTransactionLink.REVIEW_SUGGESTED,
            confidence__gte=threshold,
        )
        count = qs.update(
            review_status=NFTransactionLink.REVIEW_ACCEPTED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        # Bulk update bypasses save(): bump_version explicitly.
        try:
            from accounting.services.report_cache import bump_version
            bump_version(tenant.id)
        except Exception:
            pass
        return Response({'accepted': count})


class InvoiceNFLinkViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = InvoiceNFLink.objects.all().select_related('invoice', 'nota_fiscal')
    serializer_class = InvoiceNFLinkSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        invoice_id = params.get('invoice')
        if invoice_id:
            try:
                qs = qs.filter(invoice_id=int(invoice_id))
            except (TypeError, ValueError):
                pass
        nf_id = params.get('nota_fiscal')
        if nf_id:
            try:
                qs = qs.filter(nota_fiscal_id=int(nf_id))
            except (TypeError, ValueError):
                pass
        return qs

    def perform_destroy(self, instance):
        invoice = instance.invoice
        super().perform_destroy(instance)
        try:
            from billing.services.fiscal_status_service import refresh
            refresh(invoice, persist=True)
        except Exception:
            pass


class BillingTenantConfigViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """Singleton-per-tenant settings; the UI fetches via /current/ for upsert."""
    queryset = BillingTenantConfig.objects.all()
    serializer_class = BillingTenantConfigSerializer

    @action(methods=['get', 'put', 'patch'], detail=False, url_path='current')
    def current(self, request, **kwargs):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)
        instance, _ = BillingTenantConfig.objects.get_or_create(company=tenant)
        if request.method == 'GET':
            return Response(BillingTenantConfigSerializer(instance).data)
        partial = request.method == 'PATCH'
        serializer = BillingTenantConfigSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)