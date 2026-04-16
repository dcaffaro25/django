"""
Fetch configuration for ERPSyncJob: static params, date windows, incremental cursor.

fetch_config JSON shape (all keys optional except where noted):

{
  "mode": "pagination_only" | "date_windows" | "incremental_dates",
  "static_params": {},           # merged over extra_params (static_params wins)
  "max_segments_per_run": 100,   # safety cap for date_windows and incremental_dates
  "timezone": "America/Sao_Paulo",
  "date_dimension": {
    "from_key": "dDtIncDe",
    "to_key": "dDtIncAte",
    "format": "dd/MM/yyyy",
    "window_days": 7,
    "step_days": 7               # default: same as window_days
  },
  "bounds": {
    "start": "2025-01-01",       # ISO date (YYYY-MM-DD)
    "end": "2025-12-31",         # optional hard cap; default computed dynamically
    "end_offset_days": -1        # dynamic end = today + offset (default -1 = yesterday)
  },
  "cursor": {
    "next_start": "2025-06-01"   # incremental_dates: first day of next window
  }
}

incremental_dates catch-up: yields ALL segments from cursor to bound_end in a
single execution (capped by max_segments_per_run). The caller is responsible
for advancing the cursor per-segment after success (see omie_sync_service).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Tuple

from django.utils import timezone

MODE_PAGINATION_ONLY = "pagination_only"
MODE_DATE_WINDOWS = "date_windows"
MODE_INCREMENTAL_DATES = "incremental_dates"

DEFAULT_MAX_SEGMENTS = 200
DEFAULT_TIMEZONE = "America/Sao_Paulo"


def merge_static_params(job: Any) -> Dict[str, Any]:
    """Merge extra_params with fetch_config.static_params (latter wins)."""
    out: Dict[str, Any] = dict(job.extra_params or {})
    fc = job.fetch_config or {}
    static = fc.get("static_params")
    if isinstance(static, dict):
        out.update(static)
    return out


def _tz(fc: Dict[str, Any]):
    try:
        from zoneinfo import ZoneInfo

        name = fc.get("timezone") or DEFAULT_TIMEZONE
        return ZoneInfo(name)
    except Exception:
        return timezone.get_current_timezone()


def _today_in_tz(fc: Dict[str, Any]) -> date:
    tz = _tz(fc)
    return timezone.now().astimezone(tz).date()


def _parse_iso_date(s: Any) -> Optional[date]:
    if s is None:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    text = str(s).strip()[:10]
    if not text:
        return None
    return date.fromisoformat(text)


def format_date_param(d: date, fmt: str) -> str:
    if fmt == "dd/MM/yyyy":
        return d.strftime("%d/%m/%Y")
    return d.isoformat()


def validate_fetch_config(fc: Optional[Dict[str, Any]]) -> List[str]:
    """Return human-readable validation errors (empty = ok)."""
    errors: List[str] = []
    if not fc:
        return errors
    if not isinstance(fc, dict):
        return ["fetch_config must be a JSON object."]

    mode = fc.get("mode", MODE_PAGINATION_ONLY)
    if mode not in (MODE_PAGINATION_ONLY, MODE_DATE_WINDOWS, MODE_INCREMENTAL_DATES):
        errors.append(f"fetch_config.mode must be one of: pagination_only, date_windows, incremental_dates (got {mode!r}).")

    sp = fc.get("static_params")
    if sp is not None and not isinstance(sp, dict):
        errors.append("fetch_config.static_params must be an object.")

    if mode in (MODE_DATE_WINDOWS, MODE_INCREMENTAL_DATES):
        dim = fc.get("date_dimension") or {}
        if not isinstance(dim, dict):
            errors.append("fetch_config.date_dimension must be an object when mode uses dates.")
        else:
            for key in ("from_key", "to_key"):
                if not dim.get(key) or not str(dim.get(key)).strip():
                    errors.append(f"fetch_config.date_dimension.{key} is required for date modes.")
            wd = dim.get("window_days")
            if wd is not None:
                try:
                    w = int(wd)
                    if w < 1 or w > 3660:
                        errors.append("fetch_config.date_dimension.window_days must be between 1 and 3660.")
                except (TypeError, ValueError):
                    errors.append("fetch_config.date_dimension.window_days must be an integer.")

    bounds = fc.get("bounds")
    if bounds is not None and not isinstance(bounds, dict):
        errors.append("fetch_config.bounds must be an object.")
    elif isinstance(bounds, dict):
        eod = bounds.get("end_offset_days")
        if eod is not None:
            try:
                v = int(eod)
                if v > 0:
                    errors.append("fetch_config.bounds.end_offset_days must be <= 0 (0=today, -1=yesterday).")
            except (TypeError, ValueError):
                errors.append("fetch_config.bounds.end_offset_days must be an integer.")

    if fc.get("max_segments_per_run") is not None:
        try:
            m = int(fc["max_segments_per_run"])
            if m < 1 or m > 10000:
                errors.append("fetch_config.max_segments_per_run must be between 1 and 10000.")
        except (TypeError, ValueError):
            errors.append("fetch_config.max_segments_per_run must be an integer.")

    return errors


@dataclass
class Segment:
    """One API param overlay for a date window."""

    params: Dict[str, Any]
    label: str
    date_start: date
    date_end: date


def iter_fetch_segments(job: Any) -> Iterator[Segment]:
    """
    Yield segments to run (each with its own pagination loop).
    pagination_only -> one segment with empty param overlay.
    """
    fc = job.fetch_config or {}
    mode = fc.get("mode", MODE_PAGINATION_ONLY)

    if mode == MODE_PAGINATION_ONLY:
        yield Segment(params={}, label="default", date_start=_today_in_tz(fc), date_end=_today_in_tz(fc))
        return

    dim = fc.get("date_dimension") or {}
    from_key = str(dim.get("from_key", "")).strip()
    to_key = str(dim.get("to_key", "")).strip()
    fmt = str(dim.get("format") or "dd/MM/yyyy").strip() or "dd/MM/yyyy"
    window_days = int(dim.get("window_days") or 1)
    step_days = dim.get("step_days")
    if step_days is None:
        step_days = window_days
    step_days = int(step_days)
    if window_days < 1:
        window_days = 1
    if step_days < 1:
        step_days = 1

    bounds = fc.get("bounds") or {}
    bound_start = _parse_iso_date(bounds.get("start"))
    bound_end_fixed = _parse_iso_date(bounds.get("end"))

    max_seg = int(fc.get("max_segments_per_run") or DEFAULT_MAX_SEGMENTS)
    today = _today_in_tz(fc)

    default_offset = -1 if mode == MODE_INCREMENTAL_DATES else 0
    end_offset = int(bounds.get("end_offset_days", default_offset))
    dynamic_end = today + timedelta(days=end_offset)

    if bound_end_fixed is not None:
        bound_end = min(bound_end_fixed, dynamic_end)
    else:
        bound_end = dynamic_end

    if bound_start is None:
        bound_start = today - timedelta(days=window_days - 1)

    if bound_start > bound_end:
        return

    def overlay(d0: date, d1: date) -> Dict[str, Any]:
        return {
            from_key: format_date_param(d0, fmt),
            to_key: format_date_param(d1, fmt),
        }

    if mode == MODE_INCREMENTAL_DATES:
        cursor = (fc.get("cursor") or {}) if isinstance(fc.get("cursor"), dict) else {}
        next_s = _parse_iso_date(cursor.get("next_start"))
        if next_s is None:
            next_s = bound_start
        if next_s > bound_end:
            return
        cur = next_s
        count = 0
        while cur <= bound_end and count < max_seg:
            win_end = min(cur + timedelta(days=window_days - 1), bound_end)
            label = f"{cur.isoformat()}..{win_end.isoformat()}"
            yield Segment(params=overlay(cur, win_end), label=label, date_start=cur, date_end=win_end)
            count += 1
            cur = cur + timedelta(days=step_days)
        return

    # date_windows: backfill many segments in one run
    cur = bound_start
    count = 0
    while cur <= bound_end and count < max_seg:
        win_end = min(cur + timedelta(days=window_days - 1), bound_end)
        label = f"{cur.isoformat()}..{win_end.isoformat()}"
        yield Segment(params=overlay(cur, win_end), label=label, date_start=cur, date_end=win_end)
        count += 1
        cur = cur + timedelta(days=step_days)


def next_cursor_after_incremental(segment: Segment) -> Dict[str, Any]:
    """Cursor dict to store after a successful incremental_dates run."""
    nxt = segment.date_end + timedelta(days=1)
    return {"next_start": nxt.isoformat()}


def coalesce_segments(job: Any) -> List[Segment]:
    return list(iter_fetch_segments(job))
