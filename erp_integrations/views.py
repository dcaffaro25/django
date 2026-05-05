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
from .filters import ERPRawRecordFilter, apply_advanced_raw_record_filter, apply_json_field_filters
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
    APIDefinitionTestCallRequestSerializer,
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


def _merge_discovered_api_candidate(existing: ERPAPIDefinition, candidate: dict) -> list[str]:
    """Conservatively enrich an existing API definition from discovery output.

    Discovery can be noisy, so this only fills missing structured fields and
    appends newly found params by name. It never removes operator-entered
    params or overwrites credentials/auth-sensitive choices.
    """
    changed: list[str] = []

    doc_url = candidate.get("documentation_url")
    if doc_url and not existing.documentation_url:
        existing.documentation_url = doc_url
        changed.append("documentation_url")

    description = (candidate.get("description") or "")[:255]
    if description and not existing.description:
        existing.description = description
        changed.append("description")

    records_path = candidate.get("records_path")
    if records_path and not existing.records_path:
        existing.records_path = records_path
        changed.append("records_path")

    pagination_spec = candidate.get("pagination_spec")
    if pagination_spec and not existing.pagination_spec:
        existing.pagination_spec = pagination_spec
        changed.append("pagination_spec")

    existing_params = list(existing.param_schema or [])
    by_name = {
        p.get("name"): dict(p)
        for p in existing_params
        if isinstance(p, dict) and p.get("name")
    }
    appended = False
    for param in candidate.get("param_schema") or []:
        if not isinstance(param, dict) or not param.get("name"):
            continue
        name = param["name"]
        current = by_name.get(name)
        if current is None:
            existing_params.append(param)
            by_name[name] = dict(param)
            appended = True
            continue
        enriched_param = dict(current)
        touched = False
        for key in ("type", "description", "default", "required", "location", "options"):
            value = param.get(key)
            if value not in (None, "", []) and enriched_param.get(key) in (None, "", []):
                enriched_param[key] = value
                touched = True
        if touched:
            for idx, row in enumerate(existing_params):
                if isinstance(row, dict) and row.get("name") == name:
                    existing_params[idx] = enriched_param
                    break
            by_name[name] = enriched_param
            appended = True

    if appended:
        existing.param_schema = existing_params
        changed.append("param_schema")

    if changed:
        existing.source = ERPAPIDefinition.SOURCE_DISCOVERED
        changed.append("source")

    return changed


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


class ERPAPIDefinitionViewSet(SoftDeleteQuerysetMixin, viewsets.ModelViewSet):
    """CRUD for API definitions (global, not tenant-scoped).

    Phase-1 of the Sandbox API plan promoted this viewset from
    ReadOnly to full CRUD so the structured editor can create / update
    definitions through the UI instead of the Django admin. Backwards-
    compatible: ``list`` / ``retrieve`` payload shape is unchanged
    (just gains the new metadata fields).

    Two custom actions:

    * ``POST /api-definitions/validate/`` — runs validators against a
      hypothetical payload without persisting. Used by the editor to
      light up errors next to fields as the operator types.
    * ``POST /api-definitions/{id}/test-call/`` — fires a single real
      call against the chosen connection, redacts the response, and
      returns ``infer_response_columns`` output for the auto-probe
      surface. Updates ``last_tested_at`` / ``last_test_outcome`` on
      the definition.
    """

    queryset = (
        ERPAPIDefinition.objects
        .filter(is_active=True)
        .select_related("provider")
        .order_by("provider__slug", "call")
    )
    serializer_class = ERPAPIDefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        provider_id = self.request.query_params.get("provider")
        if provider_id:
            qs = qs.filter(provider_id=provider_id)
        # Show inactive too when the editor explicitly asks for them
        # (the ``is_active=False`` filter at the queryset top is the
        # default for callers that want only-active rows).
        if self.request.query_params.get("include_inactive") == "1":
            qs = ERPAPIDefinition.objects.select_related("provider").order_by("provider__slug", "call")
            if provider_id:
                qs = qs.filter(provider_id=provider_id)
        return qs

    @action(detail=False, methods=["post"], url_path="discover")
    def discover(self, request, tenant_id=None):
        """Phase-2: discover candidate APIs from a documentation URL.

        Body: ``{ url: str, provider?: int, allow_llm?: bool }``.

        Doesn't persist anything — returns ``{strategy_used,
        candidates: [...]}`` for the operator to review and import
        via ``import_discovered`` below. ``provider`` is informational
        only at this layer; gets set on each candidate at import time.

        ``allow_llm`` requires the tenant's billing config to enable
        ``allow_llm_doc_parse`` (mirrors the plan's safety guard).
        """
        from .services.api_discovery_service import discover_from_url

        url = (request.data or {}).get("url", "").strip()
        if not url:
            return Response(
                {"detail": "url é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allow_llm_requested = bool((request.data or {}).get("allow_llm"))
        # Tenant gate: only honour allow_llm when the tenant's billing
        # config explicitly opts in. Falls back to disabled silently.
        allow_llm = False
        if allow_llm_requested:
            tenant = getattr(request, "tenant", None)
            try:
                from billing.models_config import BillingTenantConfig
                if tenant and tenant != "all":
                    cfg = BillingTenantConfig.objects.filter(company=tenant).first()
                    if cfg and getattr(cfg, "allow_llm_doc_parse", False):
                        allow_llm = True
            except Exception:
                allow_llm = False

        # We don't ship a default LLM caller here — the wiring would
        # need an Anthropic SDK config that isn't always present. The
        # operator can stick to the OpenAPI / Postman / HTML strategies
        # which cover most cases; LLM is plumbed but inert by default.
        result = discover_from_url(url, allow_llm=allow_llm, llm_caller=None)
        return Response(result.to_dict())

    @action(detail=False, methods=["post"], url_path="import-discovered")
    def import_discovered(self, request, tenant_id=None):
        """Persist a list of operator-selected candidates as
        ``ERPAPIDefinition`` rows, sourced as ``discovered``.

        Body: ``{ provider: int, candidates: [{call, method, url,
        description, param_schema, ...}, ...] }``. Each candidate is
        validated; failures are reported per-row but don't block the
        rest from importing.
        """
        from .services.api_definition_service import (
            validate_param_schema, validate_pagination_spec,
        )

        body = request.data or {}
        provider_id = body.get("provider")
        candidates = body.get("candidates") or []
        mode = body.get("mode") or "create_only"
        if not provider_id:
            return Response({"detail": "provider é obrigatório."}, status=400)
        if mode not in {"create_only", "enrich_existing", "upsert"}:
            return Response({"detail": "mode invalido."}, status=400)
        if not isinstance(candidates, list) or not candidates:
            return Response({"detail": "candidates não pode ser vazio."}, status=400)

        created: list = []
        enriched: list = []
        failed: list = []
        for i, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                failed.append({"index": i, "error": "candidate must be an object"})
                continue
            row_errors: list = []
            ps_errors = validate_param_schema(cand.get("param_schema") or [])
            if ps_errors:
                row_errors.extend([f"param_schema: {e}" for e in ps_errors])
            pg_errors = validate_pagination_spec(cand.get("pagination_spec"))
            if pg_errors:
                row_errors.extend([f"pagination_spec: {e}" for e in pg_errors])
            if row_errors:
                failed.append({"index": i, "call": cand.get("call"), "errors": row_errors})
                continue

            # Skip if (provider, call) already exists — operator can edit
            # the existing one rather than creating a duplicate.
            existing = ERPAPIDefinition.objects.filter(
                provider_id=provider_id, call=cand.get("call"),
            ).first()
            if existing:
                if mode != "create_only":
                    changes = _merge_discovered_api_candidate(existing, cand)
                    if changes:
                        existing.save(update_fields=changes)
                    enriched.append({"id": existing.id, "call": existing.call, "fields": changes})
                    continue
                failed.append({
                    "index": i, "call": cand.get("call"),
                    "errors": [f"já existe (id={existing.id}). Edite-a manualmente."],
                })
                continue

            if mode == "enrich_existing":
                failed.append({
                    "index": i, "call": cand.get("call"),
                    "errors": ["nao existe cadastro para enriquecer."],
                })
                continue

            try:
                obj = ERPAPIDefinition.objects.create(
                    provider_id=provider_id,
                    call=cand.get("call") or f"discovered_{i}",
                    method=(cand.get("method") or "GET").upper(),
                    url=cand.get("url") or "",
                    description=(cand.get("description") or "")[:255],
                    param_schema=cand.get("param_schema") or [],
                    auth_strategy=cand.get("auth_strategy") or "provider_default",
                    pagination_spec=cand.get("pagination_spec") or None,
                    records_path=cand.get("records_path") or "",
                    documentation_url=cand.get("documentation_url") or None,
                    source=ERPAPIDefinition.SOURCE_DISCOVERED,
                    is_active=False,  # operator promotes to active after review
                )
                created.append({"id": obj.id, "call": obj.call})
            except Exception as exc:
                failed.append({
                    "index": i, "call": cand.get("call"),
                    "errors": [f"{type(exc).__name__}: {exc}"],
                })

        return Response({
            "created": created,
            "created_count": len(created),
            "enriched": enriched,
            "enriched_count": len(enriched),
            "failed": failed,
            "failed_count": len(failed),
        })

    @action(detail=False, methods=["post"], url_path="validate")
    def validate_definition(self, request, tenant_id=None):
        """Run validators against the supplied payload without saving.

        Returns ``{"ok": bool, "errors": {field: [msg, ...]}}`` so the
        UI can paint inline indicators. Helpful while iterating on a
        new definition before committing it.
        """
        from .services.api_definition_service import (
            validate_param_schema, validate_pagination_spec,
        )
        body = request.data or {}
        errors = {}
        ps_errors = validate_param_schema(body.get("param_schema"))
        if ps_errors:
            errors["param_schema"] = ps_errors
        pg_errors = validate_pagination_spec(body.get("pagination_spec"))
        if pg_errors:
            errors["pagination_spec"] = pg_errors
        ok = not errors
        return Response({"ok": ok, "errors": errors})

    @action(detail=True, methods=["post"], url_path="test-call")
    def test_call(self, request, pk=None, tenant_id=None):
        """Make one real call and return the response shape.

        Body: ``{connection_id, param_values?, max_pages?}`` (validated
        by ``APIDefinitionTestCallRequestSerializer``).

        Reuses ``execute_pipeline_spec`` from the existing pipeline
        executor so retries / unwrapping stay identical to production
        runs. Wraps the single api_definition into a 1-step inline
        pipeline; caps at ``max_pages`` and 1 fanout.
        """
        from django.utils import timezone as dj_tz
        from .services.api_definition_service import infer_response_columns
        from .services.pipeline_service import (
            _PipelineCaps, execute_pipeline_spec,
        )

        api_def = self.get_object()
        req = APIDefinitionTestCallRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = req.validated_data

        tenant = getattr(request, "tenant", None)
        company_id = None
        if tenant and tenant != "all" and hasattr(tenant, "id"):
            company_id = tenant.id
        if not company_id:
            return Response(
                {"detail": "test-call requires an explicit tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        caps = _PipelineCaps(
            max_steps=1,
            max_pages_per_step=int(data.get("max_pages") or 1),
            max_fanout=1,
        )
        spec_result = execute_pipeline_spec(
            connection_id=data["connection_id"],
            steps=[{
                "order": 1,
                "api_definition_id": api_def.id,
                "extra_params": data.get("param_values") or {},
                "param_bindings": [],
                "select_fields": None,
            }],
            company_id=company_id,
            caps=caps,
        )

        outcome = ERPAPIDefinition.OUTCOME_SUCCESS
        last_error = ""
        if not spec_result.get("success"):
            err_text = (spec_result.get("error") or "").lower()
            if "auth" in err_text or "unauthorized" in err_text or "401" in err_text:
                outcome = ERPAPIDefinition.OUTCOME_AUTH_FAIL
            else:
                outcome = ERPAPIDefinition.OUTCOME_ERROR
            last_error = (spec_result.get("error") or "")[:2000]

        ERPAPIDefinition.objects.filter(pk=api_def.pk).update(
            last_tested_at=dj_tz.now(),
            last_test_outcome=outcome,
            last_test_error=last_error,
        )

        # Pull the first preview rows + first redacted payload so the
        # operator can see the actual response shape immediately.
        preview = (spec_result.get("preview_by_step") or [{}])[0] if spec_result.get("preview_by_step") else {}
        preview_rows = preview.get("rows") or []
        # Build the canonical "columns" view either from the redacted
        # payload (if available) or the extracted rows.
        first_payload = spec_result.get("first_payload_redacted")
        if first_payload:
            shape = infer_response_columns(first_payload, api_def.records_path or None)
        else:
            shape = infer_response_columns(preview_rows[0] if preview_rows else None)

        return Response({
            "ok": spec_result.get("success", False),
            "outcome": outcome,
            "error": spec_result.get("error"),
            "diagnostics": spec_result.get("diagnostics"),
            "preview_rows": preview_rows[:5],
            "shape": shape,
            "first_payload_redacted": first_payload,
        })


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
            qs = apply_json_field_filters(qs, self.request.query_params)
            return apply_advanced_raw_record_filter(qs, self.request.query_params.get("advanced_filter"))
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

    # ---- Phase-4: scheduled routines ----

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None, tenant_id=None):
        """Soft-disable scheduled fires without losing the schedule."""
        pipeline = self.get_object()
        pipeline.is_paused = True
        pipeline.save(update_fields=["is_paused"])
        return Response({"is_paused": True})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None, tenant_id=None):
        """Re-enable scheduled fires."""
        pipeline = self.get_object()
        pipeline.is_paused = False
        pipeline.save(update_fields=["is_paused"])
        return Response({"is_paused": False})

    @action(detail=True, methods=["post"], url_path="run-now")
    def run_now(self, request, pk=None, tenant_id=None):
        """Synchronously fire the scheduled-runner for this pipeline.

        Body: ``{ force_full_dump?: bool, window_start?, window_end? }``.
        Returns the ``ScheduledRunOutcome`` dict so the UI can show what
        window was used and whether the run advanced the high-watermark.

        Distinct from the existing ``/run/`` action which queues via
        Celery — this one runs inline so the operator sees the outcome
        immediately. For long pipelines, prefer the queued path.
        """
        from .services.pipeline_scheduler import run_scheduled_pipeline

        pipeline = self.get_object()
        body = request.data or {}
        explicit_window = None
        ws = body.get("window_start")
        we = body.get("window_end")
        if ws and we:
            from django.utils.dateparse import parse_datetime
            explicit_window = (parse_datetime(ws), parse_datetime(we))

        outcome = run_scheduled_pipeline(
            pipeline.id,
            triggered_by="manual",
            force_full_dump=bool(body.get("force_full_dump")),
            explicit_window=explicit_window,
        )
        return Response(outcome.to_dict())

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None, tenant_id=None):
        """Recent runs for this pipeline. Default 50, ordered by most
        recent. Operators land here from the routines detail page."""
        pipeline = self.get_object()
        qs = (
            ERPSyncPipelineRun.objects
            .filter(pipeline=pipeline)
            .order_by("-started_at")[:50]
        )
        data = [{
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "duration_seconds": r.duration_seconds,
            "records_extracted": r.records_extracted,
            "records_stored": r.records_stored,
            "records_skipped": r.records_skipped,
            "records_updated": r.records_updated,
            "failed_step_order": r.failed_step_order,
            "errors": r.errors,
            "triggered_by": r.triggered_by,
            "incremental_window_start": (
                r.incremental_window_start.isoformat() if r.incremental_window_start else None
            ),
            "incremental_window_end": (
                r.incremental_window_end.isoformat() if r.incremental_window_end else None
            ),
        } for r in qs]
        return Response(data)


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


class PedidoVendasReportView(APIView):
    """
    GET /<tenant>/api/erp/reports/pedidos/

    Read-side report on PedidoVendas, powered by the latest snapshot
    in ERPRawRecord (populated by the ``evolat_omie_pedidos_full``
    pipeline). Joins pedidos with clientes and produtos in memory —
    no fanout, no extra HTTP.

    Query params:
      * ``date_from`` / ``date_to`` — ISO YYYY-MM-DD
      * ``etapa`` — exact match (e.g. ``50`` for "Faturado")
      * ``codigo_cliente`` — Omie cliente id
      * ``search`` — substring match across numero, cliente, CNPJ
      * ``limit`` — default 200, hard cap 1000

    POST body: ``{"refresh": true}`` runs the pipeline first (live;
    persists ERPRawRecord upsert via unique_id_config) then returns
    the report.
    """

    def _coerce_date(self, value):
        from datetime import date as _date
        if not value:
            return None
        try:
            return _date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    def _build(self, request, tenant_id=None):
        tenant = getattr(request, "tenant", None)
        company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
        if not company_id:
            return Response(
                {"detail": "Tenant required for this report."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .services.pedido_report_service import get_pedido_report
        params = request.query_params if request.method == "GET" else request.data

        try:
            limit = max(1, min(int(params.get("limit", 200)), 1000))
        except (TypeError, ValueError):
            limit = 200

        codigo_cliente = params.get("codigo_cliente")
        try:
            codigo_cliente = int(codigo_cliente) if codigo_cliente else None
        except (TypeError, ValueError):
            codigo_cliente = None

        report = get_pedido_report(
            company_id=company_id,
            date_from=self._coerce_date(params.get("date_from")),
            date_to=self._coerce_date(params.get("date_to")),
            etapa=(params.get("etapa") or None),
            codigo_cliente=codigo_cliente,
            search=(params.get("search") or None),
            limit=limit,
        )
        return Response(report, status=status.HTTP_200_OK)

    def get(self, request, tenant_id=None):
        return self._build(request, tenant_id=tenant_id)

    def post(self, request, tenant_id=None):
        # POST with ``{"refresh": true}`` triggers a live pipeline run
        # (upserts ERPRawRecord via unique_id_config) before returning
        # the latest snapshot.
        if request.data.get("refresh"):
            tenant = getattr(request, "tenant", None)
            company_id = getattr(tenant, "id", None) if tenant and tenant != "all" else None
            if not company_id:
                return Response(
                    {"detail": "Tenant required to refresh."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            from .models import ERPSyncPipeline
            from .services.pipeline_service import execute_pipeline

            pipeline = ERPSyncPipeline.objects.filter(
                company_id=company_id, name="evolat_omie_pedidos_full",
                is_active=True,
            ).first()
            if not pipeline:
                return Response(
                    {"detail": "Pipeline 'evolat_omie_pedidos_full' not configured for this tenant."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            run_result = execute_pipeline(pipeline_id=pipeline.id, dry_run=False)
            if run_result.get("status") == "failed":
                return Response(
                    {
                        "detail": "Pipeline run failed; report shows previous snapshot.",
                        "run_result": run_result,
                        "report": self._build(request, tenant_id=tenant_id).data,
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return self._build(request, tenant_id=tenant_id)
