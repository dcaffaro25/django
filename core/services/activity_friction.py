"""Friction-signal detectors for the admin dashboard.

Four independent scans over the event stream, each designed to
surface one kind of "something's wrong with the workflow" hint.
All heuristics — the goal is to be a jumping-off point for
admin investigation, not a ground-truth alarm.

Signals:

  * ``back_and_forth``  — user bounced A → B → A within a short
    window. Smells like "couldn't find what I needed on B".
  * ``long_dwell_no_action`` — session × area with meaningful
    focused time and zero business actions. Smells like "stuck on
    this screen".
  * ``repeat_errors`` — 3+ errors on the same user × area in a
    5-minute bucket. Smells like "broken thing they keep trying".
  * ``slow_actions`` — top action labels by p95 duration_ms.
    Smells like "this mutation is slow and we didn't notice".
"""

from __future__ import annotations

from datetime import timedelta
from statistics import median
from collections import defaultdict

from django.utils import timezone

from core.models import UserActivityEvent


_BACK_AND_FORTH_WINDOW_S = 60  # A→B→A within 60s to count
_MIDDLE_MAX_S = 15             # middle step lasted less than this
_LONG_DWELL_MIN_MS = 5 * 60_000
_REPEAT_ERROR_BUCKET_S = 300
_REPEAT_ERROR_THRESHOLD = 3
_TOP_N = 20


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    xs = sorted(values)
    idx = max(0, min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1)))))
    return xs[idx]


def detect_back_and_forth(*, days: int = 30) -> list[dict]:
    """Group A→B→A page_view triples by (area_a, area_b), most common first."""
    since = timezone.now() - timedelta(days=days)
    qs = (
        UserActivityEvent.objects
        .filter(created_at__gte=since, kind=UserActivityEvent.KIND_PAGE_VIEW)
        .order_by("session_id", "created_at")
        .values("session_id", "user_id", "user__username", "area", "created_at")
    )

    pair_counts: dict[tuple[str, str], dict] = defaultdict(lambda: {"count": 0, "sample_users": set()})
    # 3-event window per session
    prev2 = None
    prev1 = None
    cur_session = None
    for ev in qs.iterator():
        if ev["session_id"] != cur_session:
            cur_session = ev["session_id"]
            prev2, prev1 = None, None
        if prev2 and prev1 and prev2["area"] and prev1["area"] and ev["area"]:
            if prev2["area"] == ev["area"] and prev2["area"] != prev1["area"]:
                total = (ev["created_at"] - prev2["created_at"]).total_seconds()
                middle = (prev1["created_at"] - prev2["created_at"]).total_seconds()
                if 0 < total <= _BACK_AND_FORTH_WINDOW_S and 0 < middle <= _MIDDLE_MAX_S:
                    key = (prev2["area"], prev1["area"])
                    entry = pair_counts[key]
                    entry["count"] += 1
                    entry["sample_users"].add((ev["user_id"], ev["user__username"]))
        prev2 = prev1
        prev1 = ev

    return [
        {
            "from_area": a,
            "to_area": b,
            "count": v["count"],
            "sample_users": [{"id": uid, "username": uname} for uid, uname in list(v["sample_users"])[:5]],
        }
        for (a, b), v in sorted(pair_counts.items(), key=lambda kv: -kv[1]["count"])[:_TOP_N]
    ]


def detect_long_dwell(*, days: int = 30) -> list[dict]:
    """Sessions where focused time on an area exceeds ``_LONG_DWELL_MIN_MS``
    without any action/search event on the same session × area."""
    since = timezone.now() - timedelta(days=days)
    qs = (
        UserActivityEvent.objects
        .filter(created_at__gte=since)
        .values("session_id", "user_id", "user__username", "area", "kind", "duration_ms")
    )

    # Roll up (session, area) stats in one pass.
    buckets: dict[tuple[int, str], dict] = defaultdict(
        lambda: {"focused_ms": 0, "actions": 0, "user_id": None, "username": ""}
    )
    for ev in qs.iterator():
        key = (ev["session_id"], ev["area"])
        b = buckets[key]
        b["user_id"] = ev["user_id"]
        b["username"] = ev["user__username"]
        if ev["kind"] == UserActivityEvent.KIND_HEARTBEAT:
            b["focused_ms"] += ev["duration_ms"] or 0
        elif ev["kind"] in (UserActivityEvent.KIND_ACTION, UserActivityEvent.KIND_SEARCH):
            b["actions"] += 1

    flagged = [
        {
            "session_id": sid,
            "area": area,
            "user_id": b["user_id"],
            "username": b["username"],
            "focused_ms": b["focused_ms"],
        }
        for (sid, area), b in buckets.items()
        if b["focused_ms"] >= _LONG_DWELL_MIN_MS and b["actions"] == 0 and area
    ]
    flagged.sort(key=lambda r: r["focused_ms"], reverse=True)
    return flagged[:_TOP_N]


def detect_repeat_errors(*, days: int = 30) -> list[dict]:
    """(user, area) pairs with ≥ N errors in a rolling 5-min bucket."""
    since = timezone.now() - timedelta(days=days)
    qs = (
        UserActivityEvent.objects
        .filter(created_at__gte=since, kind=UserActivityEvent.KIND_ERROR)
        .order_by("user_id", "area", "created_at")
        .values("id", "user_id", "user__username", "area", "created_at", "meta")
    )

    # Slide a window per (user, area) and flag buckets that fill up.
    by_key: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for ev in qs.iterator():
        by_key[(ev["user_id"], ev["area"])].append(ev)

    hotspots = []
    for (uid, area), events in by_key.items():
        events.sort(key=lambda e: e["created_at"])
        i = 0
        # For each start, greedily extend window while delta ≤ bucket size.
        while i < len(events):
            j = i
            while (
                j + 1 < len(events)
                and (events[j + 1]["created_at"] - events[i]["created_at"]).total_seconds()
                <= _REPEAT_ERROR_BUCKET_S
            ):
                j += 1
            size = j - i + 1
            if size >= _REPEAT_ERROR_THRESHOLD:
                hotspots.append({
                    "user_id": uid,
                    "username": events[i]["user__username"],
                    "area": area,
                    "errors": size,
                    "first_at": events[i]["created_at"],
                    "last_at": events[j]["created_at"],
                    "sample_messages": [
                        (e.get("meta") or {}).get("message") if isinstance(e.get("meta"), dict) else None
                        for e in events[i:j + 1][:3]
                    ],
                })
                i = j + 1  # don't double-count inside same chain
            else:
                i += 1
    hotspots.sort(key=lambda r: r["errors"], reverse=True)
    return hotspots[:_TOP_N]


def detect_slow_actions(*, days: int = 30) -> list[dict]:
    """Action labels ranked by p95 duration_ms (min 10 samples)."""
    since = timezone.now() - timedelta(days=days)
    qs = (
        UserActivityEvent.objects
        .filter(
            created_at__gte=since,
            kind=UserActivityEvent.KIND_ACTION,
            duration_ms__isnull=False,
        )
        .exclude(action="")
        .values("action", "area", "duration_ms")
    )

    durations: dict[tuple[str, str], list[int]] = defaultdict(list)
    for ev in qs.iterator():
        durations[(ev["action"], ev["area"])].append(int(ev["duration_ms"]))

    out = []
    for (action, area), values in durations.items():
        if len(values) < 10:
            continue
        out.append({
            "action": action,
            "area": area,
            "samples": len(values),
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "median_ms": int(median(values)),
            "max_ms": max(values),
        })
    out.sort(key=lambda r: r["p95_ms"] or 0, reverse=True)
    return out[:_TOP_N]


def compute_friction(*, days: int = 30) -> dict:
    """Run all four detectors and return them in one payload."""
    return {
        "days": days,
        "back_and_forth": detect_back_and_forth(days=days),
        "long_dwell_no_action": detect_long_dwell(days=days),
        "repeat_errors": detect_repeat_errors(days=days),
        "slow_actions": detect_slow_actions(days=days),
    }
