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


def execute_sync(job_id: int, dry_run: bool = False) -> Dict[str, Any]:
    """
    Execute an ERPSyncJob: fetch pages from Omie API, extract records, store as ERPRawRecord.

    If dry_run=True, only process page 1 and return diagnostics without storing.
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

    # Static params + optional date (or other) overlays per segment
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
    last_incremental_segment = None
    run = None  # set when a sync run row is created

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
                "dry_run": dry_run,
                "diagnostics": diagnostics,
                "errors": [],
            }

        # Initial redacted snapshot (first page of first segment)
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
        )

        for seg in segments:
            seg_diag: Dict[str, Any] = {"label": seg.label, "pages": []}
            base_params = {**static_params, **seg.params}
            base_params.setdefault("pagina", 1)
            base_params.setdefault("registros_por_pagina", 50)

            page_num = 1
            while page_num <= MAX_PAGES:
                page_params = {**base_params, "pagina": page_num}
                payload = build_payload(
                    connection=connection,
                    api_definition=api_def,
                    param_overrides=page_params,
                )

                last_error = None
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
                            diagnostics["retries"] = diagnostics.get("retries", 0) + 1
                            logger.warning("Omie consumo redundante, retry %s in %ss", attempt + 1, wait)
                            time.sleep(wait)
                            continue
                        resp.raise_for_status()
                        raw = resp.json()
                        break
                    except requests.RequestException as e:
                        last_error = str(e)
                        if attempt < MAX_RETRIES_CONSUMO - 1:
                            wait = RETRY_BASE_SECONDS ** (attempt + 1)
                            time.sleep(wait)
                            continue
                        raise

                unwrapped = _unwrap_omie_response(raw)
                header, records, pnum, total_pages, total_records = _extract_page_header_and_records(
                    unwrapped, records_path, config
                )

                if diagnostics.get("picked_path") is None:
                    diagnostics["picked_path"] = records_path or "auto"

                total_pages_seen = max(total_pages_seen, total_pages)
                pages_fetched += 1
                total_extracted += len(records)

                page_records_count = len(records)

                if not dry_run:
                    for i, rec in enumerate(records):
                        h = _record_hash(rec)
                        ext_id = extract_external_id(rec, uid_cfg) if uid_cfg else None

                        if not uid_cfg:
                            ERPRawRecord.objects.create(
                                company_id=company_id,
                                sync_run=run,
                                api_call=api_def.call,
                                page_number=pnum,
                                record_index=i,
                                global_index=global_index,
                                page_records_count=page_records_count,
                                total_pages=total_pages,
                                total_records=total_records,
                                page_response_header=header,
                                data=rec,
                                record_hash=h,
                            )
                            total_stored += 1
                            global_index += 1
                            continue

                        if not ext_id:
                            ERPRawRecord.objects.create(
                                company_id=company_id,
                                sync_run=run,
                                api_call=api_def.call,
                                page_number=pnum,
                                record_index=i,
                                global_index=global_index,
                                page_records_count=page_records_count,
                                total_pages=total_pages,
                                total_records=total_records,
                                page_response_header=header,
                                data=rec,
                                record_hash=h,
                                external_id=None,
                                is_duplicate=False,
                            )
                            total_stored += 1
                            global_index += 1
                            continue

                        on_dup = uid_cfg.get("on_duplicate") or "update"
                        if on_dup == "add":
                            ERPRawRecord.objects.create(
                                company_id=company_id,
                                sync_run=run,
                                api_call=api_def.call,
                                page_number=pnum,
                                record_index=i,
                                global_index=global_index,
                                page_records_count=page_records_count,
                                total_pages=total_pages,
                                total_records=total_records,
                                page_response_header=header,
                                data=rec,
                                record_hash=h,
                                external_id=ext_id,
                                is_duplicate=False,
                            )
                            total_stored += 1
                            global_index += 1
                        elif on_dup == "flag":
                            existing_flag = _latest_raw_record_same_external(
                                company_id, api_def.call, ext_id
                            )
                            ERPRawRecord.objects.create(
                                company_id=company_id,
                                sync_run=run,
                                api_call=api_def.call,
                                page_number=pnum,
                                record_index=i,
                                global_index=global_index,
                                page_records_count=page_records_count,
                                total_pages=total_pages,
                                total_records=total_records,
                                page_response_header=header,
                                data=rec,
                                record_hash=h,
                                external_id=ext_id,
                                is_duplicate=existing_flag is not None,
                            )
                            total_stored += 1
                            global_index += 1
                        else:
                            # on_duplicate == "update"
                            existing_up = _latest_raw_record_same_external(
                                company_id, api_def.call, ext_id
                            )
                            if existing_up is None:
                                ERPRawRecord.objects.create(
                                    company_id=company_id,
                                    sync_run=run,
                                    api_call=api_def.call,
                                    page_number=pnum,
                                    record_index=i,
                                    global_index=global_index,
                                    page_records_count=page_records_count,
                                    total_pages=total_pages,
                                    total_records=total_records,
                                    page_response_header=header,
                                    data=rec,
                                    record_hash=h,
                                    external_id=ext_id,
                                    is_duplicate=False,
                                )
                                total_stored += 1
                                global_index += 1
                            elif existing_up.record_hash == h:
                                total_skipped += 1
                            else:
                                existing_up.data = rec
                                existing_up.record_hash = h
                                existing_up.sync_run = run
                                existing_up.page_number = pnum
                                existing_up.record_index = i
                                existing_up.page_records_count = page_records_count
                                existing_up.total_pages = total_pages
                                existing_up.total_records = total_records
                                existing_up.page_response_header = header
                                existing_up.is_duplicate = False
                                existing_up.fetched_at = dj_tz.now()
                                existing_up.save(
                                    update_fields=[
                                        "data",
                                        "record_hash",
                                        "sync_run",
                                        "page_number",
                                        "record_index",
                                        "page_records_count",
                                        "total_pages",
                                        "total_records",
                                        "page_response_header",
                                        "is_duplicate",
                                        "fetched_at",
                                    ]
                                )
                                total_updated += 1

                seg_diag["pages"].append({"page": pnum, "records": len(records)})
                diagnostics["pages"].append({"segment": seg.label, "page": pnum, "records": len(records)})

                if dry_run:
                    break

                if page_num >= total_pages:
                    break
                page_num += 1

            diagnostics["segments"].append(seg_diag)
            last_incremental_segment = seg

            if dry_run:
                break

        run.status = "completed"
        run.diagnostics = diagnostics
        run.errors = errors

        job.last_synced_at = run.started_at
        job.last_sync_status = "completed"
        job.last_sync_record_count = total_stored + total_updated
        update_fields = ["last_synced_at", "last_sync_status", "last_sync_record_count"]

        if (
            not dry_run
            and fc_mode == MODE_INCREMENTAL_DATES
            and last_incremental_segment is not None
        ):
            fc = copy.deepcopy(job.fetch_config or {})
            fc["cursor"] = next_cursor_after_incremental(last_incremental_segment)
            job.fetch_config = fc
            update_fields.append("fetch_config")

        job.save(update_fields=update_fields)

    except RecordExtractionError as e:
        errors.append(str(e))
        if run is not None:
            run.status = "failed"
            run.errors = errors
            run.diagnostics = diagnostics
        job.last_sync_status = "failed"
        job.save(update_fields=["last_sync_status"])
    except Exception as e:
        logger.exception("ERPSyncJob %s failed", job_id)
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
        "dry_run": dry_run,
        "diagnostics": diagnostics,
        "errors": errors,
    }
