from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend

from multitenancy.mixins import ScopedQuerysetMixin, SoftDeleteQuerysetMixin

from .erp_etl import execute_erp_etl_import
from .filters import ERPRawRecordFilter, apply_json_field_filters
from .models import (
    ERPAPIDefinition,
    ERPConnection,
    ERPRawRecord,
    ERPSyncJob,
    ERPSyncPipeline,
    ERPSyncPipelineRun,
    ERPSyncRun,
)
from .serializers import (
    BuildPayloadRequestSerializer,
    ERPAPIDefinitionSerializer,
    ERPConnectionListSerializer,
    ERPConnectionSerializer,
    ERPRawRecordSerializer,
    ERPSyncJobSerializer,
    ERPSyncPipelineRunSerializer,
    ERPSyncPipelineSerializer,
    ERPSyncRunSerializer,
    ErpEtlImportRequestSerializer,
    PipelineSandboxRequestSerializer,
)
from .services.payload_builder import build_payload_by_ids
from .services.transform_engine import extract_external_id


class ERPRawRecordDataPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ERPConnectionViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for tenant-scoped ERP connections (app_key, app_secret)."""

    queryset = ERPConnection.objects.select_related("provider", "company").order_by("provider__slug")

    def get_serializer_class(self):
        if self.action == "list":
            return ERPConnectionListSerializer
        return ERPConnectionSerializer


class ERPAPIDefinitionViewSet(SoftDeleteQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list of API definitions (global, not tenant-scoped)."""

    queryset = ERPAPIDefinition.objects.filter(is_active=True).select_related("provider").order_by("provider__slug", "call")
    serializer_class = ERPAPIDefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        provider_id = self.request.query_params.get("provider")
        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        return qs


class BuildPayloadView(APIView):
    """POST build-payload: build ERP API request JSON (call, param, app_key, app_secret)."""

    def post(self, request, tenant_id=None):
        serializer = BuildPayloadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = None
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            company_id = tenant.id

        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required to build payload."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = build_payload_by_ids(
                connection_id=data["connection_id"],
                api_definition_id=data["api_definition_id"],
                param_overrides=data.get("param_overrides") or {},
                company_id=company_id,
            )
        except ERPConnection.DoesNotExist:
            return Response(
                {"detail": "Connection not found or not accessible for this tenant."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ERPAPIDefinition.DoesNotExist:
            return Response(
                {"detail": "API definition not found or does not match connection provider."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"payload": payload}, status=status.HTTP_200_OK)


class ErpEtlImportView(APIView):
    """
    POST: Run ERP API ETL import (preview or commit).
    Body: { "mapping_id": int, "response": { ... }, "commit": bool }.
    Same flow as Excel ETL: preview first, then commit when ready.
    """

    def post(self, request, tenant_id=None):
        serializer = ErpEtlImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required for ERP ETL import."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = execute_erp_etl_import(
            company_id=company_id,
            response_payload=data["response"],
            mapping_id=data["mapping_id"],
            commit=data.get("commit", False),
            import_metadata={"source": "ErpEtlImportView", "function": "execute_erp_etl_import"},
        )
        # Early failure (mapping not found, no sheets)
        if result.get("errors"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        # Commit requested but transaction was rolled back (e.g. validation failed)
        if data.get("commit") and not result.get("committed"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class ERPSyncJobViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for ERP sync jobs. Actions: run, dry_run."""

    queryset = ERPSyncJob.objects.select_related("connection", "api_definition").order_by("name")
    serializer_class = ERPSyncJobSerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        if not obj.company_id and obj.connection:
            obj.company = obj.connection.company
            obj.save(update_fields=["company"])

    def perform_update(self, serializer):
        obj = serializer.save()
        if not obj.company_id and obj.connection:
            obj.company = obj.connection.company
            obj.save(update_fields=["company"])

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            return qs.filter(connection__company=tenant)
        return qs

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None, tenant_id=None):
        """Trigger manual sync. Returns celery task_id."""
        from .tasks import run_erp_sync_task

        job = self.get_object()
        result = run_erp_sync_task.delay(job.id)
        return Response({"task_id": str(result.id)})

    @action(detail=True, methods=["post"])
    def dry_run(self, request, pk=None, tenant_id=None):
        """Dry-run page 1 only, return diagnostics."""
        from .services.omie_sync_service import execute_sync

        job = self.get_object()
        out = execute_sync(job.id, dry_run=True)
        return Response(out)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None, tenant_id=None):
        """
        Retry a failed/partial sync. Resumes from the current cursor.
        Optional body: {"reset_cursor_to": "2026-03-10"} to rewind the cursor
        before retrying.
        """
        import copy
        from .tasks import run_erp_sync_task

        job = self.get_object()
        reset_to = request.data.get("reset_cursor_to")
        if reset_to:
            from datetime import date as _date
            try:
                parsed = _date.fromisoformat(str(reset_to).strip()[:10])
            except (ValueError, TypeError):
                return Response(
                    {"detail": "reset_cursor_to must be a valid ISO date (YYYY-MM-DD)."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            fc = copy.deepcopy(job.fetch_config or {})
            fc.setdefault("cursor", {})
            fc["cursor"]["next_start"] = parsed.isoformat()
            job.fetch_config = fc
            job.save(update_fields=["fetch_config"])

        result = run_erp_sync_task.delay(job.id)
        return Response({
            "task_id": str(result.id),
            "cursor": (job.fetch_config or {}).get("cursor"),
        })


class ERPSyncRunViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list/detail of ERP sync runs."""

    queryset = ERPSyncRun.objects.select_related("job").order_by("-started_at")
    serializer_class = ERPSyncRunSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        job_id = self.request.query_params.get("job")
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            qs = qs.filter(job__connection__company=tenant)
        if job_id:
            qs = qs.filter(job_id=job_id)
        return qs


class ERPRawRecordViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list/detail of raw records. Use django-filter + JSON path filters (data__, page_response_header__)."""

    queryset = ERPRawRecord.objects.select_related("sync_run").order_by("-fetched_at")
    serializer_class = ERPRawRecordSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = ERPRawRecordFilter

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            qs = qs.filter(company=tenant)
        return qs

    def filter_queryset(self, queryset):
        qs = super().filter_queryset(queryset)
        try:
            return apply_json_field_filters(qs, self.request.query_params)
        except DjangoValidationError as e:
            raise DRFValidationError(detail=list(e.messages))

    @action(detail=False, methods=["get"], url_path="data")
    def data(self, request, tenant_id=None):
        """
        Return only the JSON payload stored in each row's `data` field.

        - Filters: same query params as GET /raw-records/ (django-filter on model fields,
          plus dynamic keys `data__...` and `page_response_header__...` — see apply_json_field_filters).
        - Pagination: default `paginated=true` uses page / page_size (max 200 per page).
        - Plain array: `paginated=false` with optional `limit` (default 1000, max 2000).
        JSON filters are AND-only; OR across the same key uses repeated params (comma values use `in` lookup).
        """
        qs = self.filter_queryset(self.get_queryset())

        raw = request.query_params.get("paginated", "true")
        use_pagination = str(raw).strip().lower() not in ("false", "0", "no")

        if use_pagination:
            paginator = ERPRawRecordDataPagination()
            page = paginator.paginate_queryset(qs, request, view=self)
            if page is not None:
                payload = [row.data for row in page]
                return paginator.get_paginated_response(payload)
            return Response([])

        try:
            limit = int(request.query_params.get("limit", 1000))
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if limit < 1 or limit > 2000:
            return Response(
                {"detail": "limit must be between 1 and 2000."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rows = list(qs[:limit])
        return Response([row.data for row in rows])

    @action(detail=False, methods=["post"], url_path="backfill-external-id")
    def backfill_external_id(self, request, tenant_id=None):
        """
        Recompute external_id from each record's ERPAPIDefinition.unique_id_config.

        By default only rows with null/blank external_id are processed. Set
        recalculate_all=true to recompute for every raw row (still capped by limit).

        Optional body:
        - api_call: str — limit to one Omie call name
        - limit: int — max rows to process this request (default 1000, max 50000)
        - batch_size: int — alias for limit (if both sent, limit wins)
        - recalculate_all: bool — if true, include rows that already have external_id
        """
        tenant = getattr(request, "tenant", None)
        company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required to backfill ERP raw records."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        api_call = request.data.get("api_call")
        raw_limit = request.data.get("limit")
        if raw_limit is None:
            raw_limit = request.data.get("batch_size")
        try:
            limit = int(raw_limit if raw_limit is not None else 1000)
        except (TypeError, ValueError):
            return Response(
                {"detail": "limit (or batch_size) must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if limit < 1 or limit > 50000:
            return Response(
                {"detail": "limit must be between 1 and 50000."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recalculate_all = request.data.get("recalculate_all", False)
        if isinstance(recalculate_all, str):
            recalculate_all = recalculate_all.strip().lower() in ("1", "true", "yes", "on")
        else:
            recalculate_all = bool(recalculate_all)

        qs = ERPRawRecord.objects.select_related("sync_run__job__api_definition").order_by("id")
        if not recalculate_all:
            qs = qs.filter(Q(external_id__isnull=True) | Q(external_id=""))
        if company_id:
            qs = qs.filter(company_id=company_id)
        if api_call:
            qs = qs.filter(api_call=api_call)

        updated = 0
        unchanged = 0
        processed = 0
        skipped_no_definition = 0
        skipped_no_unique_id_config = 0
        skipped_no_value = 0

        for raw in qs[:limit]:
            processed += 1
            sync_run = getattr(raw, "sync_run", None)
            job = getattr(sync_run, "job", None) if sync_run else None
            api_def = getattr(job, "api_definition", None) if job else None
            if api_def is None:
                skipped_no_definition += 1
                continue

            uid_cfg = api_def.unique_id_config if isinstance(api_def.unique_id_config, dict) else None
            if not uid_cfg:
                skipped_no_unique_id_config += 1
                continue

            rec_data = raw.data if isinstance(raw.data, dict) else {}
            external_id = extract_external_id(rec_data, uid_cfg)
            if not external_id:
                skipped_no_value += 1
                continue

            prev = raw.external_id
            if prev is not None and str(prev).strip() == str(external_id).strip():
                unchanged += 1
                continue

            raw.external_id = external_id
            raw.save(update_fields=["external_id"])
            updated += 1

        return Response(
            {
                "processed": processed,
                "updated": updated,
                "unchanged": unchanged,
                "skipped_no_definition": skipped_no_definition,
                "skipped_no_unique_id_config": skipped_no_unique_id_config,
                "skipped_no_value": skipped_no_value,
                "api_call": api_call,
                "limit": limit,
                "recalculate_all": recalculate_all,
            },
            status=status.HTTP_200_OK,
        )


class ERPSyncPipelineViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for composite API pipelines. Actions: run, dry_run."""

    queryset = (
        ERPSyncPipeline.objects.select_related("connection", "connection__provider")
        .prefetch_related("steps", "steps__api_definition")
        .order_by("name")
    )
    serializer_class = ERPSyncPipelineSerializer

    def perform_create(self, serializer):
        obj = serializer.save()
        if not obj.company_id and obj.connection:
            obj.company = obj.connection.company
            obj.save(update_fields=["company"])

    def perform_update(self, serializer):
        obj = serializer.save()
        if not obj.company_id and obj.connection:
            obj.company = obj.connection.company
            obj.save(update_fields=["company"])

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            return qs.filter(connection__company=tenant)
        return qs

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None, tenant_id=None):
        """Queue full pipeline execution via Celery. Returns task_id."""
        from .tasks import run_erp_pipeline_task

        pipeline = self.get_object()
        result = run_erp_pipeline_task.delay(pipeline.id)
        return Response({"task_id": str(result.id)})

    @action(detail=True, methods=["post"])
    def dry_run(self, request, pk=None, tenant_id=None):
        """Run pipeline inline, one page per step, preview rows only."""
        from .services.pipeline_service import execute_pipeline

        pipeline = self.get_object()
        out = execute_pipeline(pipeline.id, dry_run=True)
        return Response(out)


class ERPSyncPipelineRunViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only list/detail of pipeline runs."""

    queryset = ERPSyncPipelineRun.objects.select_related("pipeline").order_by("-started_at")
    serializer_class = ERPSyncPipelineRunSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, "tenant", None)
        pipeline_id = self.request.query_params.get("pipeline")
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            qs = qs.filter(company=tenant)
        if pipeline_id:
            qs = qs.filter(pipeline_id=pipeline_id)
        return qs


class PipelineSandboxView(APIView):
    """
    POST inline pipeline spec, return preview rows + diagnostics.

    Ad-hoc execution with hard caps — does not persist a pipeline or raw
    records. Intended for the frontend sandbox page to let users compose
    and test multi-step calls before saving a pipeline.
    """

    def post(self, request, tenant_id=None):
        serializer = PipelineSandboxRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
        if not company_id and (not request.user or not request.user.is_superuser):
            return Response(
                {"detail": "Tenant (company) required for the pipeline sandbox."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.pipeline_service import (
            SANDBOX_DEFAULT_MAX_FANOUT,
            SANDBOX_DEFAULT_MAX_PAGES,
            SANDBOX_DEFAULT_MAX_STEPS,
            _PipelineCaps,
            execute_pipeline_spec,
        )

        caps = _PipelineCaps(
            max_steps=data.get("max_steps") or SANDBOX_DEFAULT_MAX_STEPS,
            max_pages_per_step=data.get("max_pages_per_step") or SANDBOX_DEFAULT_MAX_PAGES,
            max_fanout=data.get("max_fanout") or SANDBOX_DEFAULT_MAX_FANOUT,
        )

        result = execute_pipeline_spec(
            connection_id=data["connection_id"],
            steps=data["steps"],
            company_id=company_id,
            caps=caps,
        )

        if result.get("error") and not result.get("diagnostics"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
