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
    BusinessPartnerGroup, BusinessPartnerGroupMembership,
    BusinessPartnerAlias,
)
from .serializers import (
    BusinessPartnerCategorySerializer, BusinessPartnerSerializer,
    ProductServiceCategorySerializer, ProductServiceSerializer,
    ContractSerializer, InvoiceSerializer, InvoiceLineSerializer,
    NFTransactionLinkSerializer, InvoiceNFLinkSerializer,
    BillingTenantConfigSerializer, InvoiceDetailSerializer,
    InvoiceListSerializer, InvoiceLineWithContextSerializer,
    BusinessPartnerGroupSerializer, BusinessPartnerGroupMembershipSerializer,
    BusinessPartnerAliasSerializer,
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
    queryset = BusinessPartner.objects.all().prefetch_related(
        'group_memberships__group',
    )
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

    @action(methods=['get'], detail=False, url_path='consolidated')
    def consolidated(self, request, **kwargs):
        """Returns BPs grouped by economic Group.

        Each row is either a Group (when ``primary_only=1`` filter is set
        and the BP is the primary of its Group) or a standalone BP (no
        Group). Members of a Group are nested inside ``members`` so the
        frontend can render the Leroy-Merlin pattern: a single visible
        line per economic actor with an expand chevron.

        Query params:
          - partner_type: 'client' | 'vendor' | 'both'
          - is_active: 0 | 1
          - search: substring match on name or identifier
        """
        from billing.models import BusinessPartnerGroupMembership as _M
        qs = self.get_queryset()
        params = request.query_params

        partner_type = params.get('partner_type')
        if partner_type:
            qs = qs.filter(partner_type=partner_type)
        is_active = params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ('1', 'true', 'True'))
        search = params.get('search', '').strip()
        if search:
            from django.db.models import Q as _Q
            qs = qs.filter(_Q(name__icontains=search) | _Q(identifier__icontains=search))

        # Build a primary→members map and a list of standalone BPs.
        bps = list(qs.order_by('name', 'id')[:1000])
        bp_by_id = {bp.id: bp for bp in bps}

        primary_to_members: dict[int, list] = {}
        members_seen: set = set()
        primaries: list = []
        standalone: list = []

        # Get accepted memberships for the visible BPs.
        memberships = (
            _M.objects
            .filter(
                business_partner_id__in=list(bp_by_id),
                review_status=_M.REVIEW_ACCEPTED,
            )
            .select_related('group__primary_partner')
        )
        bp_to_group = {m.business_partner_id: m for m in memberships}

        for bp in bps:
            membership = bp_to_group.get(bp.id)
            if membership is None:
                standalone.append(bp)
                continue
            primary_id = membership.group.primary_partner_id
            if bp.id == primary_id:
                primaries.append(bp)
            else:
                primary_to_members.setdefault(primary_id, []).append(bp)
                members_seen.add(bp.id)

        # Edge case: a BP is a member of a Group whose primary isn't in the
        # current visible page — fetch that primary so the row can render.
        missing_primary_ids = [
            pid for pid in primary_to_members
            if pid not in bp_by_id
        ]
        if missing_primary_ids:
            extras = (
                BusinessPartner.objects
                .filter(id__in=missing_primary_ids)
                .prefetch_related('group_memberships__group')
            )
            for bp in extras:
                bp_by_id[bp.id] = bp
                primaries.append(bp)

        # Build the response shape.
        rows = []
        for primary in primaries:
            members = primary_to_members.get(primary.id, [])
            rows.append({
                'kind': 'group',
                'primary': BusinessPartnerSerializer(primary).data,
                'members': BusinessPartnerSerializer(members, many=True).data,
                'group_id': bp_to_group.get(primary.id).group_id if primary.id in bp_to_group else None,
            })
        for bp in standalone:
            rows.append({
                'kind': 'standalone',
                'primary': BusinessPartnerSerializer(bp).data,
                'members': [],
                'group_id': None,
            })
        return Response({'count': len(rows), 'results': rows})

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
    # Prefetch ``group_memberships`` so the serializer's
    # ``_accepted_membership`` walk doesn't fan out to N+1. Same
    # reason ``BusinessPartnerViewSet`` prefetches its memberships.
    queryset = ProductService.objects.all().select_related(
        'category',
    ).prefetch_related(
        'group_memberships',
        'group_memberships__group',
    )
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

    @action(methods=['get'], detail=False, url_path='revenue-cogs-report')
    def revenue_cogs_report(self, request, **kwargs):
        """Per-product revenue / volume / estimated-COGS / margin
        report for a date window.

        Query params:
          * ``date_from``, ``date_to`` — inclusive (default: last 90d).
          * ``group_by`` — ``product`` | ``consolidated`` (default) |
            ``category``.
          * ``tipo_operacao`` — 1=Saída (default), 0=Entrada.
          * ``finalidades`` — comma-separated NF finalidade ints
            counted as primary rows (default: ``1``=Normal). Devoluções
            (``finalidade=4``) always aggregate into ``returns_*``
            regardless of this filter.
          * ``min_revenue`` — float; drop rows below this revenue.
          * ``limit`` — int (default 200, max 500).

        Returns: ``{period, group_by, tipo_operacao, totals, rows[],
        notes}``.  See ``billing.services.product_pnl_service.compute_product_pnl``
        for the row shape.
        """
        from datetime import date as _date, timedelta
        from billing.services.product_pnl_service import compute_product_pnl
        from rest_framework.response import Response

        params = request.query_params

        def _parse_date(name, default):
            v = params.get(name)
            if not v:
                return default
            try:
                return _date.fromisoformat(v[:10])
            except ValueError:
                return default

        today = _date.today()
        date_from = _parse_date("date_from", today - timedelta(days=90))
        date_to = _parse_date("date_to", today)
        group_by = params.get("group_by") or "consolidated"
        if group_by not in ("product", "consolidated", "category"):
            return Response({"detail": "group_by inválido."}, status=400)
        try:
            tipo_operacao = int(params.get("tipo_operacao") or 1)
        except (TypeError, ValueError):
            tipo_operacao = 1
        finalidades_raw = (params.get("finalidades") or "1").split(",")
        finalidades: list[int] = []
        for f in finalidades_raw:
            try:
                finalidades.append(int(f.strip()))
            except (TypeError, ValueError):
                continue
        if not finalidades:
            finalidades = [1]
        try:
            min_revenue = float(params.get("min_revenue") or 0)
        except (TypeError, ValueError):
            min_revenue = 0
        try:
            limit = max(1, min(int(params.get("limit") or 200), 500))
        except (TypeError, ValueError):
            limit = 200

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response(
                {"detail": "revenue-cogs-report requer tenant explícito."},
                status=400,
            )

        result = compute_product_pnl(
            tenant,
            date_from=date_from,
            date_to=date_to,
            group_by=group_by,
            tipo_operacao=tipo_operacao,
            finalidades=finalidades,
        )
        # Apply min_revenue filter + limit at the API edge.
        rows = result.get("rows") or []
        if min_revenue > 0:
            rows = [
                r for r in rows
                if float(r.get("revenue") or 0) >= min_revenue
            ]
        result["rows"] = rows[:limit]
        result["truncated"] = len(rows) > limit
        return Response(result)

    @action(methods=['get'], detail=False, url_path='consolidated-summary')
    def consolidated_summary(self, request, **kwargs):
        """Return one row per canonical product (group primary or
        standalone) with counts of group members and the family
        category. Light-weight read for the dashboard / Produtos
        page header KPIs.

        Response shape:
        {
          "total_rows": <ProductService row count>,
          "canonical_count": <distinct primary_product_id + standalone count>,
          "in_groups": <rows that have an accepted membership>,
          "categorized": <rows with a non-null category>,
          "by_category": [
            {"category_id": int|null, "category_name": str|null, "count": int},
            ...
          ]
        }
        """
        from collections import defaultdict
        from billing.models_product_groups import (
            ProductServiceGroupMembership,
        )
        from rest_framework.response import Response

        qs = self.filter_queryset(self.get_queryset())
        rows = list(
            qs.values('id', 'category_id', 'category__name', 'is_active')
        )
        accepted_membership_ps_ids = set(
            ProductServiceGroupMembership.objects
            .filter(
                product_service__in=[r['id'] for r in rows],
                review_status=ProductServiceGroupMembership.REVIEW_ACCEPTED,
                role=ProductServiceGroupMembership.ROLE_MEMBER,
            )
            .values_list('product_service_id', flat=True)
        )
        canonical_count = len(rows) - len(accepted_membership_ps_ids)
        categorized = sum(1 for r in rows if r['category_id'])
        by_cat = defaultdict(lambda: {'count': 0, 'name': None})
        for r in rows:
            cid = r['category_id']
            by_cat[cid]['count'] += 1
            if r['category__name']:
                by_cat[cid]['name'] = r['category__name']
        return Response({
            'total_rows': len(rows),
            'canonical_count': canonical_count,
            'in_groups': len(accepted_membership_ps_ids),
            'categorized': categorized,
            'uncategorized': len(rows) - categorized,
            'by_category': [
                {'category_id': cid, 'category_name': data['name'], 'count': data['count']}
                for cid, data in sorted(
                    by_cat.items(),
                    key=lambda kv: (-kv[1]['count'], kv[0] or 0),
                )
            ],
        })

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
        # Critics filters: has_critics=1 → only invoices with at least one
        # unacknowledged critic. critics_severity=error|warning|info → only
        # those with that severity present.
        has_critics = params.get('has_critics')
        if has_critics in ('1', 'true', 'yes'):
            qs = qs.filter(critics_count__gt=0)
        critics_severity = params.get('critics_severity')
        if critics_severity in ('error', 'warning', 'info'):
            # JSONField __gt comparison varies by backend. Use the simple
            # contains pattern: severity key exists with value > 0. We exclude
            # zero-count rows to keep the query indexed by critics_count.
            qs = qs.filter(critics_count__gt=0).extra(
                where=[f"(critics_count_by_severity ->> '{critics_severity}')::int > 0"],
            )
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

    @action(methods=['get'], detail=True, url_path='critics')
    def critics(self, request, pk=None, **kwargs):
        """Coherence critics computed live from linked NFs, annotated with
        ack state. Read-only: never mutates Invoice / NF / GL state.
        Response: ``{count, by_severity, items}`` — counts are
        unacknowledged-only; ``items`` includes both with an ``acknowledged``
        flag so the UI can render acknowledged ones distinctly."""
        invoice = self.get_object()
        from billing.services.critics_service import (
            compute_critics_for_invoice, critics_to_dict,
            annotate_acknowledgements, severity_counts,
        )
        critics = compute_critics_for_invoice(invoice)
        annotate_acknowledgements(invoice, critics)
        sev = severity_counts(critics, only_unacknowledged=True)
        return Response({
            "count": sum(sev.values()),
            "total_including_acknowledged": len(critics),
            "by_severity": sev,
            "items": critics_to_dict(critics),
        })

    @action(methods=['post'], detail=True, url_path='acknowledge-critic')
    def acknowledge_critic(self, request, pk=None, **kwargs):
        """Mark a single (kind, subject_type, subject_id) tuple as
        acknowledged on this Invoice. Idempotent. Body:
            {"kind": "...", "subject_type": "...", "subject_id": N, "note": "..."}
        """
        invoice = self.get_object()
        from billing.models import CriticAcknowledgement
        kind = request.data.get('kind')
        subj_type = request.data.get('subject_type')
        subj_id = request.data.get('subject_id')
        note = request.data.get('note', '') or ''
        if not all([kind, subj_type, subj_id is not None]):
            return Response(
                {'detail': 'kind, subject_type e subject_id são obrigatórios.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ack, _created = CriticAcknowledgement.objects.update_or_create(
            company=invoice.company,
            invoice=invoice,
            kind=kind,
            subject_type=subj_type,
            subject_id=int(subj_id),
            defaults={
                'acknowledged_by': request.user if request.user.is_authenticated else None,
                'note': note,
            },
        )
        # Refresh the invoice's critics_count so the list view reflects the ack.
        try:
            from billing.services.fiscal_status_service import refresh
            refresh(invoice, persist=True)
        except Exception:
            pass
        return Response({'acknowledged': True, 'ack_id': ack.id})

    @action(methods=['delete'], detail=True, url_path='unacknowledge-critic')
    def unacknowledge_critic(self, request, pk=None, **kwargs):
        """Reverse a previous ack. Body shape matches acknowledge_critic."""
        invoice = self.get_object()
        from billing.models import CriticAcknowledgement
        kind = request.data.get('kind')
        subj_type = request.data.get('subject_type')
        subj_id = request.data.get('subject_id')
        if not all([kind, subj_type, subj_id is not None]):
            return Response(
                {'detail': 'kind, subject_type e subject_id são obrigatórios.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = CriticAcknowledgement.objects.filter(
            company=invoice.company,
            invoice=invoice,
            kind=kind,
            subject_type=subj_type,
            subject_id=int(subj_id),
        ).delete()
        try:
            from billing.services.fiscal_status_service import refresh
            refresh(invoice, persist=True)
        except Exception:
            pass
        return Response({'unacknowledged': bool(deleted)})

    @action(methods=['post'], detail=False, url_path='audit-critics')
    def audit_critics(self, request, **kwargs):
        """Sweep all (or a subset of) Invoices for the current tenant and
        return per-invoice critic counts + aggregate stats. Body (optional):
            {
              "invoice_ids": [...],         # limit scope
              "severity_in": ["error", ...], # filter items
              "only_unacknowledged": true,   # default
              "persist": true                # default; updates Invoice.critics_count
            }
        Same logic as the management command — UI runs it from the Faturas
        page action menu and shows the result in a modal.
        """
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)
        body = request.data or {}
        from billing.services.critics_service import audit_critics_for_company
        result = audit_critics_for_company(
            tenant,
            only_unacknowledged=bool(body.get('only_unacknowledged', True)),
            severity_in=tuple(body['severity_in']) if body.get('severity_in') else None,
            invoice_ids=tuple(body['invoice_ids']) if body.get('invoice_ids') else None,
            persist=bool(body.get('persist', True)),
        )
        return Response(result)

    @action(methods=['post'], detail=False, url_path='backfill-status-from-recon')
    def backfill_status_from_recon(self, request, **kwargs):
        """Promote ``Invoice.status`` to ``paid`` for sale invoices
        whose linked NF↔Tx evidence shows the cash moved.

        Body:
          ``{ "dry_run": bool, "include_non_open": bool }``

        Mirrors the ``bring_invoice_status_current`` mgmt command but
        callable from the UI -- the Faturas page button posts here.

        Returns the same counter dict the service emits, including
        ``would_promote``, ``promoted``, ``by_evidence`` breakdown,
        and a small sample of affected invoices for the operator's
        confirmation modal.
        """
        from billing.services.invoice_payment_evidence import (
            backfill_invoice_status_from_recon,
        )

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response(
                {'detail': 'Operação requer tenant explícito.'},
                status=400,
            )
        body = request.data or {}
        try:
            dry_run = bool(body.get('dry_run', True))
            include_non_open = bool(body.get('include_non_open', False))
        except Exception:
            return Response(
                {'detail': 'Corpo inválido. Esperado dry_run / include_non_open booleanos.'},
                status=400,
            )

        result = backfill_invoice_status_from_recon(
            tenant,
            only_open=not include_non_open,
            dry_run=dry_run,
        )
        return Response(result)

    @action(methods=['get'], detail=False, url_path='dso-report')
    def dso_report(self, request, **kwargs):
        """Days Sales Outstanding (DSO) + aging buckets + per-partner
        breakdown for ``[date_from, date_to]``.

        See ``billing.services.dso_report_service.compute_dso`` for the
        full payload shape. Query params:
          * ``date_from`` / ``date_to`` (default last 90d)
          * ``partner`` — restrict to one BusinessPartner id
            (single-partner mode; ``per_partner`` is then suppressed).
          * ``top_n_partners`` — cap on the per-partner block
            (default 10, max 100).
        """
        from datetime import date as _date, timedelta
        from billing.services.dso_report_service import compute_dso

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response(
                {"detail": "dso-report requer tenant explícito."},
                status=400,
            )

        params = request.query_params

        def _parse_date(name, default):
            v = params.get(name)
            if not v:
                return default
            try:
                return _date.fromisoformat(v[:10])
            except ValueError:
                return default

        today = _date.today()
        date_from = _parse_date("date_from", today - timedelta(days=90))
        date_to = _parse_date("date_to", today)
        if date_from > date_to:
            return Response(
                {"detail": "date_from deve ser <= date_to."},
                status=400,
            )

        partner_id = None
        if params.get('partner'):
            try:
                partner_id = int(params['partner'])
            except (TypeError, ValueError):
                pass
        try:
            top_n = max(1, min(int(params.get('top_n_partners') or 10), 100))
        except (TypeError, ValueError):
            top_n = 10

        return Response(compute_dso(
            tenant,
            date_from=date_from,
            date_to=date_to,
            partner_id=partner_id,
            top_n_partners=top_n,
        ))


class InvoiceLineViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = InvoiceLine.objects.all().select_related('invoice', 'product_service', 'invoice__partner')
    serializer_class = InvoiceLineSerializer

    def get_serializer_class(self):
        # List endpoint returns invoice + product context so cross-link
        # panels (e.g. "show me lines for product X") render without N+1.
        if self.action in ('list',):
            return InvoiceLineWithContextSerializer
        return InvoiceLineSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        for fk, key in (("product_service", "product_service"), ("invoice", "invoice")):
            v = params.get(key)
            if v:
                try:
                    qs = qs.filter(**{f"{fk}_id": int(v)})
                except (TypeError, ValueError):
                    pass
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
        # ``allocated_amount`` is optional; when omitted the service
        # auto-fills it for parcela links so the partial-coverage audit
        # trail stays correct without operator effort.
        accept_link(
            link,
            user=request.user,
            notes=request.data.get('notes', ''),
            allocated_amount=request.data.get('allocated_amount'),
        )
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

        Mirrors ``bulk_accept`` for the threshold-based selector — also
        runs the BP-Group suggestion hook per accepted link so that bulk
        flows don't silently bypass the consolidation pipeline.
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
        affected = list(qs.select_related('transaction', 'nota_fiscal'))
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
        if affected:
            from billing.services.nf_link_service import (
                _suggest_group_from_accepted_link,
            )
            for link in affected:
                try:
                    _suggest_group_from_accepted_link(link)
                except Exception:
                    pass
        return Response({'accepted': count})

    @action(methods=['post'], detail=False, url_path='bulk-accept')
    def bulk_accept(self, request, **kwargs):
        """Accept a curated set of suggested links by ID. Body: { ids: [...] }.

        Used by the review page's bulk-action bar (operator selects rows
        with checkboxes, hits "Aceitar selecionados"). Bypasses
        ``accept_link`` per-row to avoid N round trips, but still fires the
        BP-Group suggestion hook for each link in a single pass so future
        Group consolidations don't go missing.
        """
        return self._bulk_status_change(
            request,
            target=NFTransactionLink.REVIEW_ACCEPTED,
            run_group_hook=True,
        )

    @action(methods=['post'], detail=False, url_path='bulk-reject')
    def bulk_reject(self, request, **kwargs):
        """Reject a curated set of suggested links by ID. Body: { ids: [...] }."""
        return self._bulk_status_change(
            request,
            target=NFTransactionLink.REVIEW_REJECTED,
            run_group_hook=False,
        )

    def _bulk_status_change(self, request, *, target: str, run_group_hook: bool):
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)
        ids = request.data.get('ids') or []
        if not isinstance(ids, list) or not ids:
            return Response({'detail': 'ids (lista não vazia) é obrigatório.'}, status=400)
        try:
            ids = [int(x) for x in ids]
        except (TypeError, ValueError):
            return Response({'detail': 'ids inválidos.'}, status=400)

        from django.utils import timezone
        qs = NFTransactionLink.objects.filter(
            company=tenant,
            id__in=ids,
            review_status=NFTransactionLink.REVIEW_SUGGESTED,
        )
        affected = list(qs.select_related('transaction', 'nota_fiscal'))
        count = qs.update(
            review_status=target,
            reviewed_by=request.user if request.user.is_authenticated else None,
            reviewed_at=timezone.now(),
        )
        try:
            from accounting.services.report_cache import bump_version
            bump_version(tenant.id)
        except Exception:
            pass
        if run_group_hook and affected:
            # Mirror the per-link accept hook so grouping suggestions still
            # accumulate. Best-effort.
            from billing.services.nf_link_service import (
                _suggest_group_from_accepted_link,
            )
            for link in affected:
                try:
                    _suggest_group_from_accepted_link(link)
                except Exception:
                    pass
        return Response({'count': count, 'requested': len(ids)})


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


# ============================================================
# BusinessPartnerGroup / Membership / Alias
# ============================================================

class BusinessPartnerGroupViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD on BusinessPartnerGroup. ``memberships`` are managed via the
    ``BusinessPartnerGroupMembershipViewSet`` plus the custom actions on
    this viewset for higher-level operations (``promote-primary``,
    ``merge``)."""
    queryset = BusinessPartnerGroup.objects.all().select_related(
        'primary_partner',
    ).prefetch_related(
        'memberships__business_partner',
    )
    serializer_class = BusinessPartnerGroupSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        if params.get('is_active') is not None:
            qs = qs.filter(is_active=params.get('is_active') in ('1', 'true', 'True'))
        bp_id = params.get('business_partner')
        if bp_id:
            try:
                qs = qs.filter(memberships__business_partner_id=int(bp_id)).distinct()
            except (TypeError, ValueError):
                pass
        return qs.order_by('name', 'id')

    @action(methods=['post'], detail=True, url_path='promote-primary')
    def promote_primary(self, request, pk=None, **kwargs):
        """Move o role 'primary' para outro membership do mesmo grupo.
        Body: { membership_id }."""
        from django.db import transaction as db_transaction
        group = self.get_object()
        membership_id = request.data.get('membership_id')
        if not membership_id:
            return Response({'detail': 'membership_id é obrigatório.'}, status=400)
        try:
            new_primary_membership = group.memberships.get(pk=int(membership_id))
        except BusinessPartnerGroupMembership.DoesNotExist:
            return Response(
                {'detail': 'Membership não pertence a este grupo.'}, status=404,
            )
        if new_primary_membership.review_status != BusinessPartnerGroupMembership.REVIEW_ACCEPTED:
            return Response(
                {'detail': 'Membership precisa estar aceito antes de virar primary.'},
                status=400,
            )
        with db_transaction.atomic():
            current_primary = group.memberships.filter(
                role=BusinessPartnerGroupMembership.ROLE_PRIMARY,
            ).first()
            if current_primary is not None:
                current_primary.role = BusinessPartnerGroupMembership.ROLE_MEMBER
                current_primary.save(update_fields=['role', 'updated_at'])
            new_primary_membership.role = BusinessPartnerGroupMembership.ROLE_PRIMARY
            new_primary_membership.save(update_fields=['role', 'updated_at'])
            group.primary_partner = new_primary_membership.business_partner
            group.name = new_primary_membership.business_partner.name
            group.save(update_fields=['primary_partner', 'name', 'updated_at'])
        return Response(BusinessPartnerGroupSerializer(group).data)

    @action(methods=['post'], detail=True, url_path='merge')
    def merge(self, request, pk=None, **kwargs):
        """Mescla outro grupo nele. Move todos os memberships do grupo de
        origem para este, descartando o primary do origem (vira member).
        Body: { source_group_id }."""
        from django.db import transaction as db_transaction
        target = self.get_object()
        source_id = request.data.get('source_group_id')
        if not source_id:
            return Response({'detail': 'source_group_id é obrigatório.'}, status=400)
        try:
            source = BusinessPartnerGroup.objects.get(
                pk=int(source_id), company=target.company,
            )
        except BusinessPartnerGroup.DoesNotExist:
            return Response({'detail': 'Source group não encontrado.'}, status=404)
        if source.id == target.id:
            return Response({'detail': 'Não pode mesclar consigo mesmo.'}, status=400)

        with db_transaction.atomic():
            for membership in source.memberships.all():
                # If the BP is already a member of target, skip; otherwise
                # move it as 'member' (target keeps its primary).
                already = target.memberships.filter(
                    business_partner=membership.business_partner,
                ).first()
                if already is not None:
                    membership.delete()
                    continue
                membership.group = target
                membership.role = BusinessPartnerGroupMembership.ROLE_MEMBER
                membership.save(update_fields=['group', 'role', 'updated_at'])
            source.delete()
        target.refresh_from_db()
        return Response(BusinessPartnerGroupSerializer(target).data)

    @action(methods=['get'], detail=False, url_path='cnpj-root-clusters')
    def cnpj_root_clusters(self, request, **kwargs):
        """Surface matriz/filial clusters that share a CNPJ root but
        aren't yet wrapped in an explicit ``BusinessPartnerGroup``.

        These are the "structural" groupings we already use for matching
        and self-billing — same legal entity (PJ), different establishment.
        Returning them here lets the UI render every BP that conceptually
        belongs together, even when no review-driven Group exists yet.

        BPs already part of an *accepted* explicit Group are excluded so
        the curated and structural views don't double-show partners.
        """
        from django.db.models import Count
        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)

        # BP IDs already absorbed into an accepted explicit Group.
        absorbed_ids = set(
            BusinessPartnerGroupMembership.objects
            .filter(
                company=tenant,
                review_status=BusinessPartnerGroupMembership.REVIEW_ACCEPTED,
            )
            .values_list('business_partner_id', flat=True)
        )

        # Roots with at least 2 BPs in the tenant. Empty cnpj_root means
        # CPF/foreign id and is excluded.
        from billing.models import BusinessPartner
        root_qs = (
            BusinessPartner.objects
            .filter(company=tenant)
            .exclude(cnpj_root='')
            .exclude(cnpj_root__isnull=True)
            .values('cnpj_root')
            .annotate(n=Count('id'))
            .filter(n__gte=2)
            .order_by('-n', 'cnpj_root')
        )

        clusters = []
        for row in root_qs:
            root = row['cnpj_root']
            bps = list(
                BusinessPartner.objects
                .filter(company=tenant, cnpj_root=root)
                .order_by('id')
            )
            # Drop members already in an explicit Group.
            visible = [b for b in bps if b.id not in absorbed_ids]
            if len(visible) < 2:
                continue
            primary = visible[0]
            clusters.append({
                'cnpj_root': root,
                'size': len(visible),
                'primary': BusinessPartnerSerializer(primary).data,
                'members': BusinessPartnerSerializer(visible[1:], many=True).data,
            })
        return Response({'count': len(clusters), 'results': clusters})

    @action(methods=['post'], detail=False, url_path='materialize-cnpj-root')
    def materialize_cnpj_root(self, request, **kwargs):
        """Promote a cnpj_root cluster to a Group (idempotent).

        Body: ``{ cnpj_root: "12345678" }``. Delegates to
        ``ensure_root_group`` so the same logic powers both auto-creation
        on ``BusinessPartner.save`` and explicit user-driven materialization
        from the UI. Returns the resulting Group whether new or pre-existing.
        """
        from billing.models import BusinessPartner
        from billing.services.bp_group_service import ensure_root_group

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response({'detail': 'Operação requer tenant explícito.'}, status=400)
        root = (request.data.get('cnpj_root') or '').strip()
        if len(root) != 8 or not root.isdigit():
            return Response({'detail': 'cnpj_root deve ter 8 dígitos.'}, status=400)

        bps = list(
            BusinessPartner.objects
            .filter(company=tenant, cnpj_root=root)
            .order_by('id')
        )
        if len(bps) < 2:
            return Response({'detail': 'Cluster precisa ter ao menos 2 BPs.'}, status=400)

        # ensure_root_group will short-circuit if the BPs are already in
        # other groups; the caller can re-query if they expected a fresh row.
        group = None
        for bp in bps:
            group = ensure_root_group(bp) or group
        if group is None:
            return Response(
                {'detail': 'Todos os BPs deste root já estão em outros grupos.'},
                status=409,
            )
        return Response(
            BusinessPartnerGroupSerializer(group).data,
            status=201 if group.created_at == group.updated_at else 200,
        )


class BusinessPartnerGroupMembershipViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD on memberships + custom accept/reject actions."""
    queryset = BusinessPartnerGroupMembership.objects.all().select_related(
        'group', 'group__primary_partner', 'business_partner', 'reviewed_by',
    )
    serializer_class = BusinessPartnerGroupMembershipSerializer

    def perform_destroy(self, instance):
        """Refuse deletion of structurally pinned memberships.

        - The Group's primary can't be removed; promote another member first.
        - Auto-root members (matriz/filial materialized from cnpj_root) get
          recreated by ``BusinessPartner.save()`` anyway, so deleting them is
          pointless and confusing. The user has to change the BP's identifier
          to dissociate it.

        Other memberships (curated cross-root, alias-derived, manual) are
        freely removable.
        """
        from rest_framework.exceptions import ValidationError
        if instance.role == BusinessPartnerGroupMembership.ROLE_PRIMARY:
            raise ValidationError({
                'detail': (
                    "Não é possível remover o primary do grupo. Promova "
                    "outro membro a primary antes."
                ),
            })
        is_auto_root = any(
            (e or {}).get('method') == BusinessPartnerGroupMembership.METHOD_AUTO_ROOT
            for e in (instance.evidence or [])
        )
        if is_auto_root:
            raise ValidationError({
                'detail': (
                    "Membro auto-criado por raiz CNPJ — não pode ser removido "
                    "manualmente. Altere o identifier do parceiro para "
                    "dissociá-lo."
                ),
            })
        super().perform_destroy(instance)

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        rs = params.get('review_status')
        if rs:
            qs = qs.filter(review_status=rs)
        group = params.get('group')
        if group:
            try:
                qs = qs.filter(group_id=int(group))
            except (TypeError, ValueError):
                pass
        bp = params.get('business_partner')
        if bp:
            try:
                qs = qs.filter(business_partner_id=int(bp))
            except (TypeError, ValueError):
                pass
        merge_only = params.get('merge_only')
        if merge_only in ('1', 'true', 'True'):
            # Filter by evidence kind=merge — JSONField "@>" operator.
            qs = qs.filter(evidence__contains=[{'kind': 'merge'}])
        ordering = params.get('ordering') or '-confidence'
        return qs.order_by(ordering, '-id')

    @action(methods=['post'], detail=True, url_path='accept')
    def accept(self, request, pk=None, **kwargs):
        from django.db import transaction as db_transaction
        from django.utils import timezone
        membership = self.get_object()
        if membership.review_status == BusinessPartnerGroupMembership.REVIEW_ACCEPTED:
            return Response(BusinessPartnerGroupMembershipSerializer(membership).data)
        with db_transaction.atomic():
            membership.review_status = BusinessPartnerGroupMembership.REVIEW_ACCEPTED
            membership.reviewed_by = request.user if request.user.is_authenticated else None
            membership.reviewed_at = timezone.now()
            membership.save()
            # Reject conflicting suggestions for this BP in other groups.
            (
                BusinessPartnerGroupMembership.objects
                .filter(
                    business_partner=membership.business_partner,
                    review_status=BusinessPartnerGroupMembership.REVIEW_SUGGESTED,
                )
                .exclude(group_id=membership.group_id)
                .update(
                    review_status=BusinessPartnerGroupMembership.REVIEW_REJECTED,
                    reviewed_at=timezone.now(),
                )
            )
        membership.refresh_from_db()
        return Response(BusinessPartnerGroupMembershipSerializer(membership).data)

    @action(methods=['post'], detail=True, url_path='reject')
    def reject(self, request, pk=None, **kwargs):
        from django.utils import timezone
        membership = self.get_object()
        if membership.review_status == BusinessPartnerGroupMembership.REVIEW_REJECTED:
            return Response(BusinessPartnerGroupMembershipSerializer(membership).data)
        membership.review_status = BusinessPartnerGroupMembership.REVIEW_REJECTED
        membership.reviewed_by = request.user if request.user.is_authenticated else None
        membership.reviewed_at = timezone.now()
        membership.save()
        return Response(BusinessPartnerGroupMembershipSerializer(membership).data)


class BusinessPartnerAliasViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = BusinessPartnerAlias.objects.all().select_related(
        'business_partner', 'reviewed_by',
    )
    serializer_class = BusinessPartnerAliasSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        rs = params.get('review_status')
        if rs:
            qs = qs.filter(review_status=rs)
        kind = params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        bp = params.get('business_partner')
        if bp:
            try:
                qs = qs.filter(business_partner_id=int(bp))
            except (TypeError, ValueError):
                pass
        ordering = params.get('ordering') or '-hit_count'
        return qs.order_by(ordering, '-id')

    @action(methods=['post'], detail=True, url_path='accept')
    def accept(self, request, pk=None, **kwargs):
        from django.utils import timezone
        alias = self.get_object()
        if alias.review_status == BusinessPartnerAlias.REVIEW_ACCEPTED:
            return Response(BusinessPartnerAliasSerializer(alias).data)
        # Refuse if a different BP already owns this (kind, identifier)
        # as accepted -- conflict is per-kind, mirroring the unique
        # constraint on ``BusinessPartnerAlias`` (company, kind,
        # alias_identifier) where review_status='accepted'.
        conflict = (
            BusinessPartnerAlias.objects
            .filter(
                company=alias.company,
                kind=alias.kind,
                alias_identifier=alias.alias_identifier,
                review_status=BusinessPartnerAlias.REVIEW_ACCEPTED,
            )
            .exclude(pk=alias.pk)
            .exists()
        )
        if conflict:
            return Response(
                {'detail': 'Outro alias aceito já reivindica este identificador.'},
                status=409,
            )
        alias.review_status = BusinessPartnerAlias.REVIEW_ACCEPTED
        alias.reviewed_by = request.user if request.user.is_authenticated else None
        alias.reviewed_at = timezone.now()
        alias.save()
        return Response(BusinessPartnerAliasSerializer(alias).data)

    @action(methods=['post'], detail=True, url_path='reject')
    def reject(self, request, pk=None, **kwargs):
        from django.utils import timezone
        alias = self.get_object()
        if alias.review_status == BusinessPartnerAlias.REVIEW_REJECTED:
            return Response(BusinessPartnerAliasSerializer(alias).data)
        alias.review_status = BusinessPartnerAlias.REVIEW_REJECTED
        alias.reviewed_by = request.user if request.user.is_authenticated else None
        alias.reviewed_at = timezone.now()
        alias.save()
        return Response(BusinessPartnerAliasSerializer(alias).data)


# =====================================================================
# ProductServiceGroup viewsets — mirror the BP equivalents above.
# =====================================================================


class ProductServiceGroupViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD on ProductServiceGroup. Memberships are managed via the
    ``ProductServiceGroupMembershipViewSet`` plus the higher-level
    actions on this viewset (``promote-primary``, ``merge``)."""
    from billing.models_product_groups import ProductServiceGroup
    from billing.serializers import ProductServiceGroupSerializer
    queryset = ProductServiceGroup.objects.all().select_related(
        'primary_product',
    ).prefetch_related(
        'memberships__product_service',
    )
    serializer_class = ProductServiceGroupSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        if params.get('is_active') is not None:
            qs = qs.filter(is_active=params.get('is_active') in ('1', 'true', 'True'))
        ps_id = params.get('product_service')
        if ps_id:
            try:
                qs = qs.filter(memberships__product_service_id=int(ps_id)).distinct()
            except (TypeError, ValueError):
                pass
        return qs.order_by('name', 'id')

    @action(methods=['post'], detail=True, url_path='promote-primary')
    def promote_primary(self, request, pk=None, **kwargs):
        """Move 'primary' role to another accepted membership of this group.
        Body: { membership_id }."""
        from django.db import transaction as db_transaction
        from billing.models_product_groups import ProductServiceGroupMembership
        group = self.get_object()
        membership_id = request.data.get('membership_id')
        if not membership_id:
            return Response({'detail': 'membership_id é obrigatório.'}, status=400)
        try:
            new_primary = group.memberships.get(pk=int(membership_id))
        except ProductServiceGroupMembership.DoesNotExist:
            return Response(
                {'detail': 'Membership não pertence a este grupo.'}, status=404,
            )
        if new_primary.review_status != ProductServiceGroupMembership.REVIEW_ACCEPTED:
            return Response(
                {'detail': 'Membership precisa estar aceito antes de virar primary.'},
                status=400,
            )
        with db_transaction.atomic():
            current_primary = group.memberships.filter(
                role=ProductServiceGroupMembership.ROLE_PRIMARY,
            ).first()
            if current_primary is not None:
                current_primary.role = ProductServiceGroupMembership.ROLE_MEMBER
                current_primary.save(update_fields=['role', 'updated_at'])
            new_primary.role = ProductServiceGroupMembership.ROLE_PRIMARY
            new_primary.save(update_fields=['role', 'updated_at'])
            group.primary_product = new_primary.product_service
            group.name = new_primary.product_service.name
            group.save(update_fields=['primary_product', 'name', 'updated_at'])
        return Response(self.get_serializer(group).data)


class ProductServiceGroupMembershipViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD + accept/reject actions on product-group memberships."""
    from billing.models_product_groups import ProductServiceGroupMembership
    from billing.serializers import ProductServiceGroupMembershipSerializer
    queryset = ProductServiceGroupMembership.objects.all().select_related(
        'group', 'group__primary_product', 'product_service', 'reviewed_by',
    )
    serializer_class = ProductServiceGroupMembershipSerializer

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError
        from billing.models_product_groups import ProductServiceGroupMembership
        if instance.role == ProductServiceGroupMembership.ROLE_PRIMARY:
            raise ValidationError({
                'detail': (
                    "Não é possível remover o primary do grupo. Promova "
                    "outro membro a primary antes."
                ),
            })
        super().perform_destroy(instance)

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        rs = params.get('review_status')
        if rs:
            qs = qs.filter(review_status=rs)
        group = params.get('group')
        if group:
            try:
                qs = qs.filter(group_id=int(group))
            except (TypeError, ValueError):
                pass
        ps = params.get('product_service')
        if ps:
            try:
                qs = qs.filter(product_service_id=int(ps))
            except (TypeError, ValueError):
                pass
        ordering = params.get('ordering') or '-confidence'
        return qs.order_by(ordering, '-id')

    @action(methods=['post'], detail=True, url_path='accept')
    def accept(self, request, pk=None, **kwargs):
        from django.db import transaction as db_transaction
        from django.utils import timezone
        from decimal import Decimal
        from billing.models_product_groups import (
            ProductServiceAlias, ProductServiceGroupMembership,
        )
        from billing.serializers import ProductServiceGroupMembershipSerializer
        membership = self.get_object()
        if membership.review_status == ProductServiceGroupMembership.REVIEW_ACCEPTED:
            return Response(ProductServiceGroupMembershipSerializer(membership).data)
        with db_transaction.atomic():
            membership.review_status = ProductServiceGroupMembership.REVIEW_ACCEPTED
            membership.reviewed_by = request.user if request.user.is_authenticated else None
            membership.reviewed_at = timezone.now()
            membership.save()
            # Reject conflicting suggestions for this product in other groups.
            (
                ProductServiceGroupMembership.objects
                .filter(
                    product_service=membership.product_service,
                    review_status=ProductServiceGroupMembership.REVIEW_SUGGESTED,
                )
                .exclude(group_id=membership.group_id)
                .update(
                    review_status=ProductServiceGroupMembership.REVIEW_REJECTED,
                    reviewed_at=timezone.now(),
                )
            )
            # Self-healing dedup: when a member is accepted, teach the
            # import pipeline that the member's code (and EAN if any)
            # should resolve to the GROUP'S PRIMARY product going
            # forward. Next time an NF item arrives with that code,
            # ``_resolve_produto`` will hit the alias and skip
            # creating a new ProductService row. Idempotent via
            # get_or_create on (company, kind, alias_identifier).
            primary = membership.group.primary_product
            member = membership.product_service
            if primary is not None and member is not None and primary.id != member.id:
                if member.code:
                    ProductServiceAlias.objects.get_or_create(
                        company=membership.company,
                        kind=ProductServiceAlias.KIND_CODE,
                        alias_identifier=str(member.code).strip()[:80],
                        defaults={
                            'product_service': primary,
                            'review_status': ProductServiceAlias.REVIEW_ACCEPTED,
                            'source': ProductServiceAlias.SOURCE_NF_ITEM,
                            'confidence': Decimal('1.0'),
                            'hit_count': 1,
                            'evidence': [{
                                'method': 'auto_from_membership_accept',
                                'source_id': membership.id,
                                'at': timezone.now().isoformat(),
                            }],
                            'reviewed_at': timezone.now(),
                            'reviewed_by': membership.reviewed_by,
                        },
                    )
        membership.refresh_from_db()
        return Response(ProductServiceGroupMembershipSerializer(membership).data)

    @action(methods=['post'], detail=True, url_path='reject')
    def reject(self, request, pk=None, **kwargs):
        from django.utils import timezone
        from billing.models_product_groups import ProductServiceGroupMembership
        from billing.serializers import ProductServiceGroupMembershipSerializer
        membership = self.get_object()
        if membership.review_status == ProductServiceGroupMembership.REVIEW_REJECTED:
            return Response(ProductServiceGroupMembershipSerializer(membership).data)
        membership.review_status = ProductServiceGroupMembership.REVIEW_REJECTED
        membership.reviewed_by = request.user if request.user.is_authenticated else None
        membership.reviewed_at = timezone.now()
        membership.save()
        return Response(ProductServiceGroupMembershipSerializer(membership).data)


class ProductServiceAliasViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    from billing.models_product_groups import ProductServiceAlias
    from billing.serializers import ProductServiceAliasSerializer
    queryset = ProductServiceAlias.objects.all().select_related(
        'product_service', 'reviewed_by',
    )
    serializer_class = ProductServiceAliasSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = getattr(self.request, 'query_params', None)
        if params is None:
            return qs
        rs = params.get('review_status')
        if rs:
            qs = qs.filter(review_status=rs)
        kind = params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        ps = params.get('product_service')
        if ps:
            try:
                qs = qs.filter(product_service_id=int(ps))
            except (TypeError, ValueError):
                pass
        ordering = params.get('ordering') or '-hit_count'
        return qs.order_by(ordering, '-id')

    @action(methods=['post'], detail=True, url_path='accept')
    def accept(self, request, pk=None, **kwargs):
        from django.utils import timezone
        from billing.models_product_groups import ProductServiceAlias
        from billing.serializers import ProductServiceAliasSerializer
        alias = self.get_object()
        if alias.review_status == ProductServiceAlias.REVIEW_ACCEPTED:
            return Response(ProductServiceAliasSerializer(alias).data)
        conflict = (
            ProductServiceAlias.objects
            .filter(
                company=alias.company,
                kind=alias.kind,
                alias_identifier=alias.alias_identifier,
                review_status=ProductServiceAlias.REVIEW_ACCEPTED,
            )
            .exclude(pk=alias.pk)
            .exists()
        )
        if conflict:
            return Response(
                {'detail': 'Outro alias aceito já reivindica este identificador.'},
                status=409,
            )
        alias.review_status = ProductServiceAlias.REVIEW_ACCEPTED
        alias.reviewed_by = request.user if request.user.is_authenticated else None
        alias.reviewed_at = timezone.now()
        alias.save()
        return Response(ProductServiceAliasSerializer(alias).data)

    @action(methods=['post'], detail=True, url_path='reject')
    def reject(self, request, pk=None, **kwargs):
        from django.utils import timezone
        from billing.models_product_groups import ProductServiceAlias
        from billing.serializers import ProductServiceAliasSerializer
        alias = self.get_object()
        if alias.review_status == ProductServiceAlias.REVIEW_REJECTED:
            return Response(ProductServiceAliasSerializer(alias).data)
        alias.review_status = ProductServiceAlias.REVIEW_REJECTED
        alias.reviewed_by = request.user if request.user.is_authenticated else None
        alias.reviewed_at = timezone.now()
        alias.save()
        return Response(ProductServiceAliasSerializer(alias).data)

# =====================================================================
# Operations / Data-health dashboard endpoint.
# =====================================================================

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated


class HealthChecksView(APIView):
    """``GET /api/operacao/health-checks/`` — runs the registered
    pipeline-gap checks for the active tenant and returns the
    aggregated payload.

    Read-only and side-effect free: each check inspects its slice of
    the data and returns count + sample + suggested CTA. The dashboard
    page calls this on every load + manual refresh; checks are
    independently try/excepted so one bad check doesn't blank the
    page.

    See ``billing.services.health_check_service`` for the per-check
    implementations and how to register a new one.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id=None):
        from billing.services.health_check_service import run_health_checks

        tenant = getattr(request, 'tenant', None)
        if tenant is None or tenant == 'all':
            return Response(
                {'detail': 'health-checks requer tenant explícito.'},
                status=400,
            )
        return Response(run_health_checks(tenant))
