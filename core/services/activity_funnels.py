"""Funnel aggregation for the admin activity dashboards.

A "funnel" here is a small ordered list of event predicates
(``kind`` + optional ``area`` + optional ``action``). For each
user-session in the window, we walk events in chronological order
and advance a step pointer: once a step matches, we lock that
``reached_at`` and look for the next step. Sessions that reach
step N imply they reached every earlier step — funnels are
monotonic.

Why sessions and not users? A single user doing "open workbench
→ match" on three separate tabs is three funnel traversals, not
one. Session grain preserves that. Deduping by user would hide
the re-engagement pattern that admin cares about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from statistics import median
from typing import Iterable

from django.utils import timezone

from core.models import UserActivityEvent


# ---------------------------------------------------------------- config


@dataclass(frozen=True)
class FunnelStep:
    id: str
    label: str
    kind: str  # page_view / heartbeat / action / error / search
    area: str | None = None
    action: str | None = None

    def matches(self, ev: dict) -> bool:
        if ev["kind"] != self.kind:
            return False
        if self.area is not None and ev["area"] != self.area:
            return False
        if self.action is not None and (ev.get("action") or "") != self.action:
            return False
        return True


@dataclass(frozen=True)
class Funnel:
    id: str
    label: str
    description: str
    steps: tuple[FunnelStep, ...]


# Hardcoded starter set. Adding a new funnel is a code change —
# kept intentional so the ids stay stable (dashboards reference
# them by id). When the list grows too long, lift into a
# FunnelDefinition model with an admin editor.
FUNNELS: tuple[Funnel, ...] = (
    Funnel(
        id="recon.manual_match",
        label="Conciliação manual",
        description="Abrir Bancada e concluir uma conciliação manualmente.",
        steps=(
            FunnelStep(id="open_workbench", label="Abrir Bancada",
                      kind=UserActivityEvent.KIND_PAGE_VIEW, area="recon.workbench"),
            FunnelStep(id="match", label="Concluir conciliação",
                      kind=UserActivityEvent.KIND_ACTION, area="recon.workbench",
                      action="recon.match"),
        ),
    ),
    Funnel(
        id="bulk_reconcile",
        label="Conciliação em massa",
        description="Selecionar várias extratos e atribuir conta em massa.",
        steps=(
            FunnelStep(id="open_workbench", label="Abrir Bancada",
                      kind=UserActivityEvent.KIND_PAGE_VIEW, area="recon.workbench"),
            FunnelStep(id="mass_open", label="Abrir drawer em massa",
                      kind=UserActivityEvent.KIND_ACTION, area="recon.workbench",
                      action="recon.mass_open"),
            FunnelStep(id="mass_apply", label="Aplicar conta",
                      kind=UserActivityEvent.KIND_ACTION, area="recon.workbench",
                      action="recon.mass_apply"),
            FunnelStep(id="mass_submit", label="Criar conciliações",
                      kind=UserActivityEvent.KIND_ACTION, area="recon.workbench",
                      action="recon.mass_submit"),
        ),
    ),
    Funnel(
        id="download.bank_tx",
        label="Download extratos",
        description="Visualizar Extratos e baixar XLSX.",
        steps=(
            FunnelStep(id="open", label="Abrir Extratos",
                      kind=UserActivityEvent.KIND_PAGE_VIEW,
                      area="accounting.bank_transactions"),
            FunnelStep(id="download", label="Baixar XLSX",
                      kind=UserActivityEvent.KIND_ACTION,
                      action="download_xlsx"),
        ),
    ),
)


# ---------------------------------------------------------------- aggregation


def _percentile(values: list[int], p: float) -> int | None:
    """Simple nearest-rank percentile. ``values`` need not be sorted."""
    if not values:
        return None
    xs = sorted(values)
    # Clamp index into range
    idx = max(0, min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1)))))
    return xs[idx]


def compute_funnel(funnel: Funnel, *, days: int = 30) -> dict:
    """Compute a single funnel's step counts + inter-step timings."""
    since = timezone.now() - timedelta(days=days)

    # Pull every event in the window that might match any step in
    # this funnel, ordered by (session, created_at). We do the
    # step-pointer walk in Python — the predicate language isn't
    # worth pushing into SQL for the volumes we care about.
    kinds = tuple({s.kind for s in funnel.steps})
    qs = (
        UserActivityEvent.objects
        .filter(created_at__gte=since, kind__in=kinds)
        .order_by("session_id", "created_at")
        .values("id", "session_id", "user_id", "created_at", "kind", "area", "action")
    )

    # Per-session state: current step index + per-step reached_at.
    step_count = len(funnel.steps)
    step_reached: list[int] = [0] * step_count
    # inter-step timings: times_between[i] = [ms] for step i → i+1
    times_between: list[list[int]] = [[] for _ in range(max(0, step_count - 1))]

    cur_session = None
    cur_step = 0
    cur_reached_at: list[object | None] = [None] * step_count

    def _finalise():
        # Walk cur_reached_at and record timings where adjacent steps both matched.
        for i in range(step_count - 1):
            a, b = cur_reached_at[i], cur_reached_at[i + 1]
            if a is not None and b is not None:
                # ``a``/``b`` are datetimes
                delta_ms = int((b - a).total_seconds() * 1000)
                if delta_ms >= 0:
                    times_between[i].append(delta_ms)

    for ev in qs.iterator():
        if ev["session_id"] != cur_session:
            if cur_session is not None:
                _finalise()
            cur_session = ev["session_id"]
            cur_step = 0
            cur_reached_at = [None] * step_count

        if cur_step >= step_count:
            continue

        step = funnel.steps[cur_step]
        if step.matches(ev):
            cur_reached_at[cur_step] = ev["created_at"]
            for i in range(cur_step, step_count):
                # Conceptually every earlier step is also "reached" for
                # counting purposes — but we keep times only when the
                # exact event matched.
                pass
            step_reached[cur_step] += 1
            cur_step += 1

    if cur_session is not None:
        _finalise()

    # Step counts are cumulative: reaching step N implies reaching
    # steps 0..N-1 (we only advance if each matched in order). The
    # step_reached array is already cumulative-per-step because we
    # increment on match.
    step_totals = step_reached[:]
    # Sessions that reached the earliest step count as the denominator
    # for drop-off — if nobody ever entered the funnel, every "%" is
    # just zero-divided noise.
    entered = step_totals[0] if step_totals else 0
    completed = step_totals[-1] if step_totals else 0

    step_payload = []
    for idx, step in enumerate(funnel.steps):
        reached = step_totals[idx]
        prev = step_totals[idx - 1] if idx > 0 else entered
        dropoff_pct = None
        if idx > 0 and prev > 0:
            dropoff_pct = round(100 * (prev - reached) / prev, 1)
        timing = {}
        if idx > 0:
            vs = times_between[idx - 1]
            if vs:
                timing = {
                    "p50_ms": _percentile(vs, 50),
                    "p95_ms": _percentile(vs, 95),
                    "median_ms": int(median(vs)),
                    "samples": len(vs),
                }
        step_payload.append({
            "id": step.id,
            "label": step.label,
            "reached": reached,
            "dropoff_pct": dropoff_pct,
            "timing_from_previous": timing,
        })

    overall_pct = round(100 * completed / entered, 1) if entered else None
    return {
        "id": funnel.id,
        "label": funnel.label,
        "description": funnel.description,
        "entered": entered,
        "completed": completed,
        "overall_pct": overall_pct,
        "steps": step_payload,
    }


def compute_all_funnels(days: int = 30) -> list[dict]:
    return [compute_funnel(f, days=days) for f in FUNNELS]
