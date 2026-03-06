"""
Omie sync service: fetch paginated API responses, extract records, store raw JSON.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from erp_integrations.models import ERPRawRecord, ERPSyncJob, ERPSyncRun
from erp_integrations.services.payload_builder import build_payload
from erp_integrations.services.transform_engine import (
    DEFAULT_TRANSFORM_CONFIG,
    RecordExtractionError,
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

    config = dict(api_def.transform_config or {})
    config = {**DEFAULT_TRANSFORM_CONFIG, **config}
    records_config = config.get("records", {}) or {}
    records_path = records_config.get("path")

    # Build initial payload
    base_params = dict(job.extra_params or {})
    base_params.setdefault("pagina", 1)
    base_params.setdefault("registros_por_pagina", 50)

    payload = build_payload(
        connection=connection,
        api_definition=api_def,
        param_overrides=base_params,
    )
    run = ERPSyncRun.objects.create(
        job=job,
        company_id=company_id,
        status="running",
        request_payload_redacted=_redact_payload(payload),
    )

    diagnostics: Dict[str, Any] = {
        "picked_path": None,
        "retries": 0,
        "pages": [],
    }

    total_extracted = 0
    total_stored = 0
    global_index = 0
    errors: List[str] = []
    pages_fetched = 0
    total_pages_seen = 1

    try:
        page_num = 1
        while page_num <= MAX_PAGES:
            page_params = {**base_params, "pagina": page_num}
            payload = build_payload(
                connection=connection,
                api_definition=api_def,
                param_overrides=page_params,
            )

            # Request with retry for consumo redundante
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

            total_pages_seen = total_pages
            pages_fetched += 1
            total_extracted += len(records)

            page_records_count = len(records)

            if not dry_run:
                for i, rec in enumerate(records):
                    h = _record_hash(rec)
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

            diagnostics["pages"].append({"page": pnum, "records": len(records)})

            if dry_run:
                break

            if page_num >= total_pages:
                break
            page_num += 1

        run.status = "completed"
        run.pages_fetched = pages_fetched
        run.total_pages = total_pages_seen
        run.records_extracted = total_extracted
        run.records_stored = total_stored
        run.diagnostics = diagnostics
        run.errors = errors

        job.last_synced_at = run.started_at
        job.last_sync_status = "completed"
        job.last_sync_record_count = total_stored
        job.save(update_fields=["last_synced_at", "last_sync_status", "last_sync_record_count"])

    except RecordExtractionError as e:
        errors.append(str(e))
        run.status = "failed"
        run.errors = errors
        run.diagnostics = diagnostics
        job.last_sync_status = "failed"
        job.save(update_fields=["last_sync_status"])
    except Exception as e:
        logger.exception("ERPSyncJob %s failed", job_id)
        errors.append(str(e))
        run.status = "failed"
        run.errors = errors
        run.diagnostics = diagnostics
        job.last_sync_status = "failed"
        job.save(update_fields=["last_sync_status"])

    from django.utils import timezone

    run.completed_at = timezone.now()
    if run.started_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()
    run.save(update_fields=["status", "pages_fetched", "total_pages", "records_extracted", "records_stored", "errors", "diagnostics", "completed_at", "duration_seconds"])

    return {
        "success": run.status == "completed",
        "run_id": run.id,
        "status": run.status,
        "pages_fetched": pages_fetched,
        "records_extracted": total_extracted,
        "records_stored": total_stored,
        "dry_run": dry_run,
        "diagnostics": diagnostics,
        "errors": errors,
    }
