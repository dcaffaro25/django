"""
Omie sync service: fetch paginated API responses, extract records, store raw JSON.
"""

import copy
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.utils import timezone as dj_tz

from erp_integrations.models import ERPRawRecord, ERPSyncJob, ERPSyncRun
from erp_integrations.services.fetch_config import (
    MODE_INCREMENTAL_DATES,
    merge_static_params,
    coalesce_segments,
    next_cursor_after_incremental,
)
from erp_integrations.services.payload_builder import build_payload
from erp_integrations.services.transform_engine import (
    DEFAULT_TRANSFORM_CONFIG,
    RecordExtractionError,
    extract_external_id,
    pick_items_array,
)

logger = logging.getLogger(__name__)

MAX_PAGES = 200
MAX_RETRIES_CONSUMO = 3
RETRY_BASE_SECONDS = 2
REDACT_PLACEHOLDER = "***REDACTED***"


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Copy payload and mask app_key, app_secret."""
    out = dict(payload)
    if "app_key" in out and out["app_key"]:
        out["app_key"] = REDACT_PLACEHOLDER
    if "app_secret" in out and out["app_secret"]:
        out["app_secret"] = REDACT_PLACEHOLDER
    if "param" in out and isinstance(out["param"], list) and out["param"]:
        # param is a list of objects; some Omie APIs put app_key/app_secret in param[0]
        p0 = dict(out["param"][0]) if isinstance(out["param"][0], dict) else {}
        if "app_key" in p0:
            p0 = {**p0, "app_key": REDACT_PLACEHOLDER}
        if "app_secret" in p0:
            p0 = {**p0, "app_secret": REDACT_PLACEHOLDER}
        out["param"] = [p0] + list(out["param"][1:])
    return out


def _unwrap_omie_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap {statusCode, data, ...} wrapper. Return data if present, else raw."""
    if isinstance(raw.get("data"), dict):
        return raw["data"]
    if isinstance(raw.get("data"), list):
        return {"data": raw["data"]}
    return raw


def _is_consumo_redundante_error(response: requests.Response) -> bool:
    """Check if response indicates Omie 'consumo redundante' rate limit."""
    if response.status_code != 500:
        return False
    try:
        body = response.json()
        if isinstance(body, dict):
            # Omie SOAP-style fault
            fault = body.get("faultstring", "") or body.get("fault", {})
            if isinstance(fault, dict):
                fault = fault.get("faultstring", "")
            return "consumo redundante" in str(fault).lower()
    except Exception:
        pass
    return False


def _build_header_excluding_records(data: Any, records: List[Dict[str, Any]]) -> Any:
    """
    Copy data structure, recursively excluding the key that points to records (identity).
    """
    if data is records:
        return None
    if isinstance(data, dict):
        out: Dict[str, Any] = {}
        for k, v in data.items():
            if v is records:
                continue
            sub = _build_header_excluding_records(v, records)
            if sub is not None:
                out[k] = sub
        return out
    return data


def fetch_and_parse_page(
    connection,
    api_def,
    page_params: Dict[str, Any],
    config: Dict[str, Any],
    records_path: Optional[str],
    retries_counter: Optional[Dict[str, int]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int, int, int, Dict[str, Any]]:
    """
    One-page HTTP fetch + parse (shared by job sync and pipeline executor).

    Returns: (header, records, page_num, total_pages, total_records, unwrapped_response).
    Increments retries_counter["count"] on Omie 'consumo redundante' retries.
    Raises requests exceptions on unrecoverable failures.
    """
    payload = build_payload(
        connection=connection,
        api_definition=api_def,
        param_overrides=page_params,
    )

    raw: Optional[Dict[str, Any]] = None
    for attempt in range(MAX_RETRIES_CONSUMO):
        try:
            resp = requests.post(
                api_def.url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            if _is_consumo_redundante_error(resp) and attempt < MAX_RETRIES_CONSUMO - 1:
                wait = RETRY_BASE_SECONDS ** (attempt + 1)
                if retries_counter is not None:
                    retries_counter["count"] = retries_counter.get("count", 0) + 1
                logger.warning("Omie consumo redundante, retry %s in %ss", attempt + 1, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            raw = resp.json()
            break
        except requests.RequestException:
            if attempt < MAX_RETRIES_CONSUMO - 1:
                wait = RETRY_BASE_SECONDS ** (attempt + 1)
                time.sleep(wait)
                continue
            raise

    unwrapped = _unwrap_omie_response(raw or {})
    header, records, pnum, total_pages, total_records = _extract_page_header_and_records(
        unwrapped, records_path, config
    )
    return header, records, pnum, total_pages, total_records, unwrapped


def _extract_page_header_and_records(
    page_data: Dict[str, Any],
    records_path: Optional[str],
    config: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], int, int, int]:
    """
    Extract page header (all non-record keys) and the records array.
    Returns (page_response_header, records, page_num, total_pages, total_records).
    """
    records = pick_items_array(page_data, config)
    header = _build_header_excluding_records(page_data, records) or {}

    page_num = header.get("pagina") if isinstance(header, dict) else None
    total_pages = header.get("total_de_paginas") if isinstance(header, dict) else None
    registros = header.get("registros") if isinstance(header, dict) else None
    total_records = header.get("total_de_registros") if isinstance(header, dict) else None

    if page_num is None:
        page_num = 1
    if total_pages is None:
        total_pages = 1
    if registros is None:
        registros = len(records)
    if total_records is None:
        total_records = len(records)

    return header, records, int(page_num), int(total_pages), int(total_records)


def _record_hash(data: Dict[str, Any]) -> str:
    """SHA256 of canonical JSON (sorted keys)."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _latest_raw_record_same_external(
    company_id: int,
    api_call: str,
    external_id: str,
) -> Optional[ERPRawRecord]:
    """Most recent raw row for same company, api_call, and external_id."""
    return (
        ERPRawRecord.objects.filter(
            company_id=company_id,
            api_call=api_call,
            external_id=external_id,
        )
        .order_by("-fetched_at", "-id")
        .first()
    )


def _store_record(
    rec: Dict[str, Any],
    uid_cfg: Optional[Dict[str, Any]],
    company_id: int,
    run: ERPSyncRun,
    api_call: str,
    pnum: int,
    record_index: int,
    global_index: int,
    page_records_count: int,
    total_pages: int,
    total_records: int,
    header: Dict[str, Any],
) -> str:
    """
    Store a single raw record, handling dedup logic.
    Returns "stored", "skipped", or "updated".
    """
    h = _record_hash(rec)
    ext_id = extract_external_id(rec, uid_cfg) if uid_cfg else None

    base_kwargs = dict(
        company_id=company_id,
        sync_run=run,
        api_call=api_call,
        page_number=pnum,
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

    if on_dup == "flag":
        existing = _latest_raw_record_same_external(company_id, api_call, ext_id)
        ERPRawRecord.objects.create(**base_kwargs, external_id=ext_id, is_duplicate=existing is not None)
        return "stored"

    # on_duplicate == "update"
    existing = _latest_raw_record_same_external(company_id, api_call, ext_id)
    if existing is None:
        ERPRawRecord.objects.create(**base_kwargs, external_id=ext_id, is_duplicate=False)
        return "stored"
    if existing.record_hash == h:
        return "skipped"

    existing.data = rec
    existing.record_hash = h
    existing.sync_run = run
    existing.page_number = pnum
    existing.record_index = record_index
    existing.page_records_count = page_records_count
    existing.total_pages = total_pages
    existing.total_records = total_records
    existing.page_response_header = header
    existing.is_duplicate = False
    existing.fetched_at = dj_tz.now()
    existing.save(update_fields=[
        "data", "record_hash", "sync_run", "page_number", "record_index",
        "page_records_count", "total_pages", "total_records",
        "page_response_header", "is_duplicate", "fetched_at",
    ])
    return "updated"


def _fetch_segment_pages(
    seg,
    static_params: Dict[str, Any],
    connection,
    api_def,
    config: Dict[str, Any],
    records_path: Optional[str],
    uid_cfg: Optional[Dict[str, Any]],
    company_id: int,
    run: ERPSyncRun,
    diagnostics: Dict[str, Any],
    global_index: int,
    dry_run: bool,
) -> Dict[str, Any]:
    """
    Fetch all pages for one segment. Returns counters dict.
    Raises on unrecoverable errors.
    """
    seg_diag: Dict[str, Any] = {"label": seg.label, "pages": []}
    base_params = {**static_params, **seg.params}
    base_params.setdefault("pagina", 1)
    base_params.setdefault("registros_por_pagina", 50)

    extracted = 0
    stored = 0
    skipped = 0
    updated = 0
    pages = 0
    max_total_pages = 1
    idx = global_index

    page_num = 1
    retries_counter = {"count": diagnostics.get("retries", 0)}
    while page_num <= MAX_PAGES:
        page_params = {**base_params, "pagina": page_num}
        header, records, pnum, total_pages, total_records, _unwrapped = fetch_and_parse_page(
            connection=connection,
            api_def=api_def,
            page_params=page_params,
            config=config,
            records_path=records_path,
            retries_counter=retries_counter,
        )
        diagnostics["retries"] = retries_counter["count"]

        if diagnostics.get("picked_path") is None:
            diagnostics["picked_path"] = records_path or "auto"

        max_total_pages = max(max_total_pages, total_pages)
        pages += 1
        extracted += len(records)
        page_records_count = len(records)

        if not dry_run:
            for i, rec in enumerate(records):
                outcome = _store_record(
                    rec, uid_cfg, company_id, run, api_def.call,
                    pnum, i, idx, page_records_count, total_pages, total_records, header,
                )
                if outcome == "stored":
                    stored += 1
                    idx += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1

        seg_diag["pages"].append({"page": pnum, "records": len(records)})
        diagnostics["pages"].append({"segment": seg.label, "page": pnum, "records": len(records)})

        if dry_run or page_num >= total_pages:
            break
        page_num += 1

    diagnostics["segments"].append(seg_diag)

    return {
        "extracted": extracted,
        "stored": stored,
        "skipped": skipped,
        "updated": updated,
        "pages": pages,
        "max_total_pages": max_total_pages,
        "global_index": idx,
    }


def execute_sync(job_id: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Execute an ERPSyncJob: fetch pages from Omie API, extract records, store as ERPRawRecord.

    For incremental_dates mode, processes all pending segments (catch-up) in a
    single execution, advancing the cursor after each successful segment and
    stopping immediately on the first error.

    If dry_run=True, only process page 1 of the first segment without storing.
    """
    job = ERPSyncJob.objects.select_related("connection", "api_definition").filter(pk=job_id).first()
    if not job:
        return {"success": False, "error": f"ERPSyncJob id={job_id} not found"}

    connection = job.connection
    api_def = job.api_definition
    company_id = connection.company_id
    uid_cfg = api_def.unique_id_config if isinstance(api_def.unique_id_config, dict) else None

    config = dict(api_def.transform_config or {})
    config = {**DEFAULT_TRANSFORM_CONFIG, **config}
    records_config = config.get("records", {}) or {}
    records_path = records_config.get("path")

    static_params = merge_static_params(job)
    segments = coalesce_segments(job)
    fc_mode = (job.fetch_config or {}).get("mode", "pagination_only")

    diagnostics: Dict[str, Any] = {
        "picked_path": None,
        "retries": 0,
        "pages": [],
        "segments": [],
        "fetch_mode": fc_mode,
    }

    total_extracted = 0
    total_stored = 0
    total_skipped = 0
    total_updated = 0
    global_index = 0
    errors: List[str] = []
    pages_fetched = 0
    total_pages_seen = 1
    segments_completed = 0
    failed_segment_label: Optional[str] = None
    last_successful_segment = None
    run: Optional[ERPSyncRun] = None

    try:
        if not segments:
            run = ERPSyncRun.objects.create(
                job=job,
                company_id=company_id,
                status="completed",
                request_payload_redacted={},
                diagnostics=diagnostics,
                records_extracted=0,
                records_stored=0,
                records_skipped=0,
                records_updated=0,
                pages_fetched=0,
                segments_total=0,
                segments_completed=0,
            )
            diagnostics["message"] = "No segments to fetch (check bounds and cursor)."
            run.diagnostics = diagnostics
            run.save(update_fields=["diagnostics"])
            job.last_synced_at = run.started_at
            job.last_sync_status = "completed"
            job.last_sync_record_count = 0
            job.save(update_fields=["last_synced_at", "last_sync_status", "last_sync_record_count"])

            run.completed_at = dj_tz.now()
            if run.started_at:
                run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
            run.save(update_fields=["completed_at", "duration_seconds"])
            return {
                "success": True,
                "run_id": run.id,
                "status": run.status,
                "pages_fetched": 0,
                "records_extracted": 0,
                "records_stored": 0,
                "records_skipped": 0,
                "records_updated": 0,
                "segments_total": 0,
                "segments_completed": 0,
                "dry_run": dry_run,
                "diagnostics": diagnostics,
                "errors": [],
            }

        segments_total = len(segments)

        first_base = {**static_params, **segments[0].params}
        first_base.setdefault("pagina", 1)
        first_base.setdefault("registros_por_pagina", 50)
        first_payload = build_payload(
            connection=connection,
            api_definition=api_def,
            param_overrides=first_base,
        )
        run = ERPSyncRun.objects.create(
            job=job,
            company_id=company_id,
            status="running",
            request_payload_redacted=_redact_payload(first_payload),
            segments_total=segments_total,
        )

        for seg in segments:
            try:
                result = _fetch_segment_pages(
                    seg, static_params, connection, api_def, config,
                    records_path, uid_cfg, company_id, run, diagnostics,
                    global_index, dry_run,
                )
            except (RecordExtractionError, requests.RequestException, Exception) as e:
                logger.warning(
                    "ERPSyncJob %s segment %s failed: %s", job_id, seg.label, e
                )
                errors.append(f"Segment {seg.label}: {e}")
                failed_segment_label = seg.label
                break

            total_extracted += result["extracted"]
            total_stored += result["stored"]
            total_skipped += result["skipped"]
            total_updated += result["updated"]
            pages_fetched += result["pages"]
            total_pages_seen = max(total_pages_seen, result["max_total_pages"])
            global_index = result["global_index"]

            segments_completed += 1
            last_successful_segment = seg

            # Advance cursor after each successful incremental segment
            if (
                not dry_run
                and fc_mode == MODE_INCREMENTAL_DATES
                and last_successful_segment is not None
            ):
                fc = copy.deepcopy(job.fetch_config or {})
                fc["cursor"] = next_cursor_after_incremental(last_successful_segment)
                job.fetch_config = fc
                job.save(update_fields=["fetch_config"])

            if dry_run:
                break

        if failed_segment_label:
            run.status = "partial" if segments_completed > 0 else "failed"
            job.last_sync_status = run.status
        else:
            run.status = "completed"
            job.last_sync_status = "completed"

        run.diagnostics = diagnostics
        run.errors = errors

        job.last_synced_at = run.started_at
        job.last_sync_record_count = total_stored + total_updated
        job.save(update_fields=["last_synced_at", "last_sync_status", "last_sync_record_count"])

    except Exception as e:
        logger.exception("ERPSyncJob %s failed unexpectedly", job_id)
        errors.append(str(e))
        if run is not None:
            run.status = "failed"
            run.errors = errors
            run.diagnostics = diagnostics
        job.last_sync_status = "failed"
        job.save(update_fields=["last_sync_status"])

    if run is not None:
        run.pages_fetched = pages_fetched
        run.total_pages = total_pages_seen
        run.records_extracted = total_extracted
        run.records_stored = total_stored
        run.records_skipped = total_skipped
        run.records_updated = total_updated
        run.segments_completed = segments_completed
        run.failed_segment_label = failed_segment_label
        run.completed_at = dj_tz.now()
        if run.started_at:
            run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
        run.save(
            update_fields=[
                "status",
                "pages_fetched",
                "total_pages",
                "records_extracted",
                "records_stored",
                "records_skipped",
                "records_updated",
                "segments_completed",
                "failed_segment_label",
                "errors",
                "diagnostics",
                "completed_at",
                "duration_seconds",
            ]
        )

    return {
        "success": (run.status == "completed") if run is not None else False,
        "run_id": run.id if run is not None else None,
        "status": run.status if run is not None else "failed",
        "pages_fetched": pages_fetched,
        "records_extracted": total_extracted,
        "records_stored": total_stored,
        "records_skipped": total_skipped,
        "records_updated": total_updated,
        "segments_total": len(segments),
        "segments_completed": segments_completed,
        "failed_segment": failed_segment_label,
        "dry_run": dry_run,
        "diagnostics": diagnostics,
        "errors": errors,
    }
