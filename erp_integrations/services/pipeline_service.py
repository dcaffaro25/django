"""
Composite pipeline executor.

An ERPSyncPipeline is an ordered list of ERPSyncPipelineSteps, each wrapping
one ERPAPIDefinition. Param bindings let step N derive params from the JSON
responses of steps 1..N-1 (static value, single JMESPath expression, or fanout
over a list expression that repeats the step once per value).

The executor reuses fetch_and_parse_page() from omie_sync_service so HTTP
retries, response unwrapping, and record extraction behave identically to the
single-job path. Raw records are persisted with both sync_run=None and
pipeline_run=<run> so downstream consumers can distinguish provenance.

Sandbox mode (execute_pipeline_spec) runs an in-memory pipeline spec with
hard caps (max steps, max pages per step, max fanout) and never persists to
ERPRawRecord. It returns preview rows plus per-step diagnostics.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import jmespath
import requests
from django.utils import timezone as dj_tz

from erp_integrations.models import (
    ERPAPIDefinition,
    ERPConnection,
    ERPRawRecord,
    ERPSyncPipeline,
    ERPSyncPipelineRun,
    ERPSyncPipelineStep,
)
from erp_integrations.services.omie_sync_service import (
    MAX_PAGES,
    _record_hash,
    _redact_payload,
    fetch_and_parse_page,
)
from erp_integrations.services.payload_builder import build_payload
from erp_integrations.services.transform_engine import (
    DEFAULT_TRANSFORM_CONFIG,
    RecordExtractionError,
    extract_external_id,
)

logger = logging.getLogger(__name__)

SANDBOX_DEFAULT_MAX_STEPS = 2
SANDBOX_DEFAULT_MAX_PAGES = 1
SANDBOX_DEFAULT_MAX_FANOUT = 50

VALID_BINDING_MODES = frozenset({"static", "jmespath", "fanout"})


class PipelineConfigError(Exception):
    """Raised when a pipeline or step spec is invalid."""


@dataclass
class _StepSpec:
    """In-memory representation of a pipeline step (DB-backed or sandbox)."""

    order: int
    api_definition: ERPAPIDefinition
    extra_params: Dict[str, Any] = field(default_factory=dict)
    param_bindings: List[Dict[str, Any]] = field(default_factory=list)
    select_fields: Optional[str] = None


@dataclass
class _PipelineCaps:
    max_steps: int = 10000
    max_pages_per_step: int = MAX_PAGES
    max_fanout: int = 10000


# ---------------------------------------------------------------------------
# Binding resolution
# ---------------------------------------------------------------------------


def _validate_binding(binding: Any, step_order: int) -> None:
    if not isinstance(binding, dict):
        raise PipelineConfigError(f"Step {step_order}: each binding must be an object.")
    mode = binding.get("mode")
    if mode not in VALID_BINDING_MODES:
        raise PipelineConfigError(
            f"Step {step_order}: binding.mode must be one of {sorted(VALID_BINDING_MODES)}; got {mode!r}."
        )
    into = binding.get("into")
    if not isinstance(into, str) or not into.strip():
        raise PipelineConfigError(f"Step {step_order}: binding.into must be a non-empty string.")
    if mode == "static":
        if "value" not in binding:
            raise PipelineConfigError(f"Step {step_order}: static binding requires 'value'.")
    else:
        expression = binding.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise PipelineConfigError(
                f"Step {step_order}: {mode} binding requires a non-empty 'expression'."
            )
        src = binding.get("source_step")
        if not isinstance(src, int) or src < 1 or src >= step_order:
            raise PipelineConfigError(
                f"Step {step_order}: {mode} binding source_step must be a prior 1-based step order."
            )


def _resolve_non_fanout_bindings(
    bindings: List[Dict[str, Any]],
    context: Dict[int, Any],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Apply static + jmespath bindings. Return (overrides, fanout_binding, resolved_log).

    fanout_binding is returned separately so the caller can expand it into
    multiple sub-runs. At most one fanout binding per step is allowed.
    """
    overrides: Dict[str, Any] = {}
    fanout: Optional[Dict[str, Any]] = None
    resolved_log: List[Dict[str, Any]] = []

    for binding in bindings:
        mode = binding["mode"]
        into = binding["into"]
        if mode == "static":
            overrides[into] = binding["value"]
            resolved_log.append({"mode": "static", "into": into, "value": binding["value"]})
            continue
        if mode == "jmespath":
            src = binding["source_step"]
            expression = binding["expression"]
            src_data = context.get(src)
            value = jmespath.search(expression, src_data) if src_data is not None else None
            overrides[into] = value
            resolved_log.append(
                {
                    "mode": "jmespath",
                    "source_step": src,
                    "expression": expression,
                    "into": into,
                    "value_preview": _preview(value),
                }
            )
            continue
        if mode == "fanout":
            if fanout is not None:
                raise PipelineConfigError("Only one fanout binding per step is supported in v1.")
            fanout = binding

    return overrides, fanout, resolved_log


def _fanout_values(
    binding: Dict[str, Any],
    context: Dict[int, Any],
    max_fanout: int,
) -> List[Any]:
    src = binding["source_step"]
    expression = binding["expression"]
    src_data = context.get(src)
    result = jmespath.search(expression, src_data) if src_data is not None else None
    if result is None:
        return []
    if not isinstance(result, list):
        raise PipelineConfigError(
            f"Fanout expression {expression!r} must resolve to a list; got {type(result).__name__}."
        )
    if len(result) > max_fanout:
        result = result[:max_fanout]
    return result


def _preview(value: Any, max_chars: int = 200) -> Any:
    """Truncate value for diagnostics logging."""
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return value


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


def _merged_base_params(step: _StepSpec, binding_overrides: Dict[str, Any]) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(step.extra_params or {})
    base.update(binding_overrides)
    base.setdefault("pagina", 1)
    base.setdefault("registros_por_pagina", 50)
    return base


def _store_pipeline_record(
    *,
    rec: Dict[str, Any],
    uid_cfg: Optional[Dict[str, Any]],
    company_id: int,
    pipeline_run: ERPSyncPipelineRun,
    step_order: int,
    api_call: str,
    page_num: int,
    record_index: int,
    global_index: int,
    page_records_count: int,
    total_pages: int,
    total_records: int,
    header: Dict[str, Any],
) -> str:
    """
    Persist one raw record for a pipeline execution. Scoped dedup by
    (company, api_call, external_id), same as single-job sync.
    """
    h = _record_hash(rec)
    ext_id = extract_external_id(rec, uid_cfg) if uid_cfg else None

    base_kwargs = dict(
        company_id=company_id,
        sync_run=None,
        pipeline_run=pipeline_run,
        pipeline_step_order=step_order,
        api_call=api_call,
        page_number=page_num,
        record_index=record_index,
        global_index=global_index,
        page_records_count=page_records_count,
        total_pages=total_pages,
        total_records=total_records,
        page_response_header=header,
        data=rec,
        record_hash=h,
    )

    if not uid_cfg or not ext_id:
        ERPRawRecord.objects.create(**base_kwargs, external_id=ext_id, is_duplicate=False)
        return "stored"

    on_dup = uid_cfg.get("on_duplicate") or "update"

    if on_dup == "add":
        ERPRawRecord.objects.create(**base_kwargs, external_id=ext_id, is_duplicate=False)
        return "stored"

    existing = (
        ERPRawRecord.objects.filter(
            company_id=company_id,
            api_call=api_call,
            external_id=ext_id,
        )
        .order_by("-fetched_at", "-id")
        .first()
    )

    if on_dup == "flag":
        ERPRawRecord.objects.create(
            **base_kwargs, external_id=ext_id, is_duplicate=existing is not None
        )
        return "stored"

    # on_duplicate == "update"
    if existing is None:
        ERPRawRecord.objects.create(**base_kwargs, external_id=ext_id, is_duplicate=False)
        return "stored"
    if existing.record_hash == h:
        return "skipped"

    existing.data = rec
    existing.record_hash = h
    existing.sync_run = None
    existing.pipeline_run = pipeline_run
    existing.pipeline_step_order = step_order
    existing.page_number = page_num
    existing.record_index = record_index
    existing.page_records_count = page_records_count
    existing.total_pages = total_pages
    existing.total_records = total_records
    existing.page_response_header = header
    existing.is_duplicate = False
    existing.fetched_at = dj_tz.now()
    existing.save(
        update_fields=[
            "data", "record_hash", "sync_run", "pipeline_run", "pipeline_step_order",
            "page_number", "record_index", "page_records_count", "total_pages",
            "total_records", "page_response_header", "is_duplicate", "fetched_at",
        ]
    )
    return "updated"


def _execute_single_step_invocation(
    *,
    connection: ERPConnection,
    step: _StepSpec,
    base_params: Dict[str, Any],
    caps: _PipelineCaps,
    company_id: Optional[int],
    pipeline_run: Optional[ERPSyncPipelineRun],
    preview_only: bool,
    global_index: int,
) -> Dict[str, Any]:
    """
    Fetch pages for one (step, resolved_params) invocation. Returns counters
    plus the full unwrapped response from the LAST page (used as context for
    downstream bindings) and optionally preview rows.
    """
    api_def = step.api_definition
    config = dict(api_def.transform_config or {})
    config = {**DEFAULT_TRANSFORM_CONFIG, **config}
    records_path = (config.get("records") or {}).get("path")
    uid_cfg = api_def.unique_id_config if isinstance(api_def.unique_id_config, dict) else None

    extracted = 0
    stored = 0
    skipped = 0
    updated = 0
    pages = 0
    retries_counter = {"count": 0}
    last_unwrapped: Dict[str, Any] = {}
    preview_rows: List[Dict[str, Any]] = []

    page_num = 1
    max_pages = min(MAX_PAGES, max(1, caps.max_pages_per_step))
    while page_num <= max_pages:
        page_params = {**base_params, "pagina": page_num}
        header, records, pnum, total_pages, total_records, unwrapped = fetch_and_parse_page(
            connection=connection,
            api_def=api_def,
            page_params=page_params,
            config=config,
            records_path=records_path,
            retries_counter=retries_counter,
        )
        last_unwrapped = unwrapped
        pages += 1
        extracted += len(records)
        page_records_count = len(records)

        if preview_only:
            preview_rows.extend(records)
        elif pipeline_run is not None and company_id is not None:
            for i, rec in enumerate(records):
                outcome = _store_pipeline_record(
                    rec=rec,
                    uid_cfg=uid_cfg,
                    company_id=company_id,
                    pipeline_run=pipeline_run,
                    step_order=step.order,
                    api_call=api_def.call,
                    page_num=pnum,
                    record_index=i,
                    global_index=global_index,
                    page_records_count=page_records_count,
                    total_pages=total_pages,
                    total_records=total_records,
                    header=header,
                )
                if outcome == "stored":
                    stored += 1
                    global_index += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1

        if page_num >= total_pages:
            break
        page_num += 1

    return {
        "extracted": extracted,
        "stored": stored,
        "skipped": skipped,
        "updated": updated,
        "pages": pages,
        "retries": retries_counter["count"],
        "last_unwrapped": last_unwrapped,
        "preview_rows": preview_rows,
        "global_index": global_index,
    }


def _apply_projection(rows: List[Dict[str, Any]], expression: Optional[str]) -> List[Any]:
    """Apply an optional JMESPath projection over the preview rows (sandbox only)."""
    if not expression or not isinstance(expression, str) or not expression.strip():
        return rows
    try:
        return jmespath.search(expression, rows) or []
    except jmespath.exceptions.JMESPathError as exc:
        raise PipelineConfigError(f"Invalid select_fields JMESPath: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _load_db_steps(pipeline: ERPSyncPipeline) -> List[_StepSpec]:
    steps = list(
        pipeline.steps.select_related("api_definition").order_by("order")
    )
    if not steps:
        raise PipelineConfigError(f"Pipeline {pipeline.id} has no steps.")
    spec: List[_StepSpec] = []
    seen_orders = set()
    for step in steps:
        if step.order in seen_orders:
            raise PipelineConfigError(f"Pipeline {pipeline.id} has duplicate step order {step.order}.")
        seen_orders.add(step.order)
        if step.api_definition.provider_id != pipeline.connection.provider_id:
            raise PipelineConfigError(
                f"Step {step.order}: api_definition provider does not match connection provider."
            )
        for b in step.param_bindings or []:
            _validate_binding(b, step.order)
        spec.append(
            _StepSpec(
                order=step.order,
                api_definition=step.api_definition,
                extra_params=dict(step.extra_params or {}),
                param_bindings=list(step.param_bindings or []),
                select_fields=step.select_fields,
            )
        )
    return spec


def _build_inline_steps(
    inline_steps: List[Dict[str, Any]],
    connection: ERPConnection,
) -> List[_StepSpec]:
    if not inline_steps:
        raise PipelineConfigError("At least one step is required.")
    spec: List[_StepSpec] = []
    for i, raw_step in enumerate(inline_steps):
        order = int(raw_step.get("order", i + 1))
        api_def_id = raw_step.get("api_definition_id")
        if not api_def_id:
            raise PipelineConfigError(f"Step {order}: api_definition_id is required.")
        api_def = (
            ERPAPIDefinition.objects.filter(pk=api_def_id, provider=connection.provider, is_active=True)
            .select_related("provider")
            .first()
        )
        if api_def is None:
            raise PipelineConfigError(
                f"Step {order}: api_definition {api_def_id} not found or does not match connection provider."
            )
        bindings = list(raw_step.get("param_bindings") or [])
        for b in bindings:
            _validate_binding(b, order)
        spec.append(
            _StepSpec(
                order=order,
                api_definition=api_def,
                extra_params=dict(raw_step.get("extra_params") or {}),
                param_bindings=bindings,
                select_fields=raw_step.get("select_fields"),
            )
        )
    spec.sort(key=lambda s: s.order)
    return spec


def _run_steps(
    *,
    connection: ERPConnection,
    steps: List[_StepSpec],
    caps: _PipelineCaps,
    pipeline_run: Optional[ERPSyncPipelineRun],
    company_id: Optional[int],
    preview_only: bool,
) -> Dict[str, Any]:
    """
    Walk steps in order, building a context dict of prior responses.

    For each step:
      - resolve static + jmespath bindings once.
      - if a fanout binding is present, invoke the step once per resolved value.
      - store records (unless preview_only).
      - record per-step diagnostics.

    Returns aggregate counters, per-step diagnostics, and (for preview) the
    rows collected from each step.
    """
    context: Dict[int, Any] = {}
    step_diagnostics: List[Dict[str, Any]] = []
    preview_by_step: List[Dict[str, Any]] = []
    totals = {"extracted": 0, "stored": 0, "skipped": 0, "updated": 0, "pages": 0, "retries": 0}
    global_index = 0
    failed_step_order: Optional[int] = None
    errors: List[str] = []
    first_payload_redacted: Optional[Dict[str, Any]] = None

    if len(steps) > caps.max_steps:
        raise PipelineConfigError(
            f"Pipeline has {len(steps)} steps; sandbox cap is {caps.max_steps}."
        )

    for step in steps:
        diag: Dict[str, Any] = {
            "order": step.order,
            "api_call": step.api_definition.call,
            "invocations": [],
            "extracted": 0,
            "stored": 0,
            "skipped": 0,
            "updated": 0,
            "pages": 0,
            "retries": 0,
        }

        try:
            overrides, fanout, resolved_log = _resolve_non_fanout_bindings(
                step.param_bindings, context
            )
        except PipelineConfigError as exc:
            errors.append(f"Step {step.order}: {exc}")
            failed_step_order = step.order
            diag["error"] = str(exc)
            step_diagnostics.append(diag)
            break
        diag["resolved_bindings"] = resolved_log

        if fanout is None:
            fanout_values = [None]
            diag["fanout"] = None
        else:
            try:
                fanout_values = _fanout_values(fanout, context, caps.max_fanout)
            except PipelineConfigError as exc:
                errors.append(f"Step {step.order}: {exc}")
                failed_step_order = step.order
                diag["error"] = str(exc)
                step_diagnostics.append(diag)
                break
            diag["fanout"] = {
                "source_step": fanout["source_step"],
                "expression": fanout["expression"],
                "into": fanout["into"],
                "value_count": len(fanout_values),
            }

        collected_rows: List[Dict[str, Any]] = []
        context_for_step: Any = None

        try:
            for value in fanout_values:
                invocation_overrides = dict(overrides)
                if fanout is not None:
                    invocation_overrides[fanout["into"]] = value
                base_params = _merged_base_params(step, invocation_overrides)

                if first_payload_redacted is None:
                    first_payload_redacted = _redact_payload(
                        build_payload(
                            connection=connection,
                            api_definition=step.api_definition,
                            param_overrides=base_params,
                        )
                    )

                result = _execute_single_step_invocation(
                    connection=connection,
                    step=step,
                    base_params=base_params,
                    caps=caps,
                    company_id=company_id,
                    pipeline_run=pipeline_run,
                    preview_only=preview_only,
                    global_index=global_index,
                )
                global_index = result["global_index"]
                diag["extracted"] += result["extracted"]
                diag["stored"] += result["stored"]
                diag["skipped"] += result["skipped"]
                diag["updated"] += result["updated"]
                diag["pages"] += result["pages"]
                diag["retries"] += result["retries"]
                diag["invocations"].append(
                    {
                        "fanout_value": _preview(value) if fanout is not None else None,
                        "pages": result["pages"],
                        "extracted": result["extracted"],
                        "stored": result["stored"],
                        "skipped": result["skipped"],
                        "updated": result["updated"],
                    }
                )
                context_for_step = result["last_unwrapped"]
                if preview_only:
                    collected_rows.extend(result["preview_rows"])
        except (RecordExtractionError, requests.RequestException, Exception) as exc:
            logger.warning("Pipeline step %s failed: %s", step.order, exc)
            errors.append(f"Step {step.order}: {exc}")
            failed_step_order = step.order
            diag["error"] = str(exc)
            step_diagnostics.append(diag)
            break

        totals["extracted"] += diag["extracted"]
        totals["stored"] += diag["stored"]
        totals["skipped"] += diag["skipped"]
        totals["updated"] += diag["updated"]
        totals["pages"] += diag["pages"]
        totals["retries"] += diag["retries"]

        context[step.order] = context_for_step

        if preview_only:
            try:
                projected = _apply_projection(collected_rows, step.select_fields)
            except PipelineConfigError as exc:
                errors.append(f"Step {step.order}: {exc}")
                failed_step_order = step.order
                diag["error"] = str(exc)
                step_diagnostics.append(diag)
                break
            preview_by_step.append(
                {
                    "order": step.order,
                    "api_call": step.api_definition.call,
                    "row_count": len(collected_rows),
                    "rows": collected_rows,
                    "projected": projected if step.select_fields else None,
                }
            )

        step_diagnostics.append(diag)

    return {
        "totals": totals,
        "step_diagnostics": step_diagnostics,
        "preview_by_step": preview_by_step,
        "failed_step_order": failed_step_order,
        "errors": errors,
        "first_payload_redacted": first_payload_redacted,
    }


def execute_pipeline(
    pipeline_id: int,
    dry_run: bool = False,
    param_overrides_by_step: Optional[Dict[int, Dict[str, Any]]] = None,
    *,
    triggered_by: str = "manual",
    incremental_window: Optional[tuple] = None,
) -> Dict[str, Any]:
    """
    Run a persisted ERPSyncPipeline. Creates an ERPSyncPipelineRun row.

    dry_run=True behaves like ERPSyncJob.dry_run: one page per step, no DB
    writes to ERPRawRecord, but still creates a pipeline run record for audit.

    ``param_overrides_by_step``: optional ``{step_order: {field: value}}``.
    Each override merges INTO the step's stored ``extra_params`` (overrides
    win on conflict). Used by scheduled tasks that need to inject a
    rolling date window for incremental sync — e.g.
    ``{1: {"filtrar_por_alteracao_de": "01/05/2026"}}`` for ListarPedidos.
    The persisted step's stored params stay unchanged; the override is
    per-run only.

    ``triggered_by`` (Phase 4): stamped onto the ``ERPSyncPipelineRun``
    so the history surface can show who fired this run. One of
    ``manual`` / ``schedule`` / ``api`` / ``sandbox``.

    ``incremental_window`` (Phase 4): ``(start, end)`` datetimes recorded
    on the run for visibility. Pure metadata — the actual filter has
    to be on ``param_overrides_by_step`` because that's what reaches the
    upstream API.
    """
    pipeline = (
        ERPSyncPipeline.objects.select_related("connection", "connection__provider")
        .filter(pk=pipeline_id)
        .first()
    )
    if pipeline is None:
        return {"success": False, "error": f"ERPSyncPipeline id={pipeline_id} not found"}

    connection = pipeline.connection
    company_id = connection.company_id

    try:
        steps = _load_db_steps(pipeline)
    except PipelineConfigError as exc:
        return {"success": False, "error": str(exc)}

    # Apply per-step param overrides if provided. Each StepSpec has
    # mutable ``extra_params`` we shallow-merge into.
    if param_overrides_by_step:
        for step in steps:
            extra_for_this = param_overrides_by_step.get(step.order)
            if extra_for_this:
                step.extra_params = {**(step.extra_params or {}), **extra_for_this}

    caps = _PipelineCaps(
        max_pages_per_step=1 if dry_run else MAX_PAGES,
        max_fanout=SANDBOX_DEFAULT_MAX_FANOUT if dry_run else 10000,
    )

    window_start = window_end = None
    if incremental_window:
        window_start, window_end = incremental_window

    run = ERPSyncPipelineRun.objects.create(
        pipeline=pipeline,
        company_id=company_id,
        status="running",
        is_sandbox=False,
        triggered_by=triggered_by or "manual",
        incremental_window_start=window_start,
        incremental_window_end=window_end,
    )

    try:
        outcome = _run_steps(
            connection=connection,
            steps=steps,
            caps=caps,
            pipeline_run=None if dry_run else run,
            company_id=company_id,
            preview_only=dry_run,
        )
    except PipelineConfigError as exc:
        run.status = "failed"
        run.errors = [str(exc)]
        run.completed_at = dj_tz.now()
        if run.started_at:
            run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
        run.save(update_fields=["status", "errors", "completed_at", "duration_seconds"])
        pipeline.last_run_status = "failed"
        pipeline.save(update_fields=["last_run_status"])
        return {"success": False, "error": str(exc), "run_id": run.id}

    totals = outcome["totals"]
    failed_step = outcome["failed_step_order"]
    errors = outcome["errors"]

    if failed_step is not None:
        run.status = "partial" if totals["stored"] + totals["updated"] > 0 else "failed"
    else:
        run.status = "completed"

    run.records_extracted = totals["extracted"]
    run.records_stored = totals["stored"]
    run.records_skipped = totals["skipped"]
    run.records_updated = totals["updated"]
    run.errors = errors
    run.diagnostics = {
        "steps": outcome["step_diagnostics"],
        "retries": totals["retries"],
        "pages": totals["pages"],
    }
    run.failed_step_order = failed_step
    run.completed_at = dj_tz.now()
    if run.started_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.save(
        update_fields=[
            "status", "records_extracted", "records_stored", "records_skipped",
            "records_updated", "errors", "diagnostics", "failed_step_order",
            "completed_at", "duration_seconds",
        ]
    )

    if not dry_run:
        pipeline.last_run_at = run.started_at
        pipeline.last_run_status = run.status
        pipeline.last_run_record_count = totals["stored"] + totals["updated"]
        pipeline.save(update_fields=["last_run_at", "last_run_status", "last_run_record_count"])

    return {
        "success": run.status == "completed",
        "run_id": run.id,
        "status": run.status,
        "records_extracted": totals["extracted"],
        "records_stored": totals["stored"],
        "records_skipped": totals["skipped"],
        "records_updated": totals["updated"],
        "failed_step_order": failed_step,
        "dry_run": dry_run,
        "diagnostics": run.diagnostics,
        "errors": errors,
        "preview_by_step": outcome["preview_by_step"] if dry_run else [],
    }


def execute_pipeline_spec(
    *,
    connection_id: int,
    steps: List[Dict[str, Any]],
    company_id: Optional[int],
    caps: Optional[_PipelineCaps] = None,
) -> Dict[str, Any]:
    """
    Sandbox entry point: run an in-memory pipeline spec, preview-only. No
    ERPSyncPipeline row is created; no ERPRawRecord is persisted.

    Caller enforces tenant scoping via company_id (connection must belong
    to that company).
    """
    qs = ERPConnection.objects.filter(pk=connection_id, is_active=True).select_related("provider")
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    connection = qs.first()
    if connection is None:
        return {"success": False, "error": "Connection not found or not accessible for this tenant."}

    try:
        step_specs = _build_inline_steps(steps, connection)
    except PipelineConfigError as exc:
        return {"success": False, "error": str(exc)}

    effective_caps = caps or _PipelineCaps(
        max_steps=SANDBOX_DEFAULT_MAX_STEPS,
        max_pages_per_step=SANDBOX_DEFAULT_MAX_PAGES,
        max_fanout=SANDBOX_DEFAULT_MAX_FANOUT,
    )

    try:
        outcome = _run_steps(
            connection=connection,
            steps=step_specs,
            caps=effective_caps,
            pipeline_run=None,
            company_id=None,
            preview_only=True,
        )
    except PipelineConfigError as exc:
        return {"success": False, "error": str(exc)}

    totals = outcome["totals"]
    failed_step = outcome["failed_step_order"]
    errors = outcome["errors"]

    status = "completed"
    if failed_step is not None:
        status = "partial" if totals["extracted"] > 0 else "failed"

    return {
        "success": status == "completed",
        "status": status,
        "records_extracted": totals["extracted"],
        "failed_step_order": failed_step,
        "errors": errors,
        "diagnostics": {
            "steps": outcome["step_diagnostics"],
            "retries": totals["retries"],
            "pages": totals["pages"],
        },
        "preview_by_step": outcome["preview_by_step"],
        "first_payload_redacted": outcome["first_payload_redacted"],
        "caps": {
            "max_steps": effective_caps.max_steps,
            "max_pages_per_step": effective_caps.max_pages_per_step,
            "max_fanout": effective_caps.max_fanout,
        },
    }
