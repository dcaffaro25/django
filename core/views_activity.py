"""Activity-beacon ingestion + read-side endpoints for the admin
dashboards.

The write path is intentionally tolerant: any authenticated user can
POST events about *themselves*, we coerce odd shapes rather than
rejecting, and we never raise on unknown fields. The read path is
gated by :class:`multitenancy.permissions.IsSuperUser` — only platform
admins see other users' activity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_tz
from typing import Any

from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import UserActivityEvent, UserActivitySession
from multitenancy.models import Company
from multitenancy.permissions import IsSuperUser


_ALLOWED_KINDS = {
    UserActivityEvent.KIND_PAGE_VIEW,
    UserActivityEvent.KIND_HEARTBEAT,
    UserActivityEvent.KIND_ACTION,
    UserActivityEvent.KIND_ERROR,
    UserActivityEvent.KIND_SEARCH,
}

_MAX_EVENTS_PER_BATCH = 200


def _clean_int(value: Any) -> int | None:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _clean_str(value: Any, *, max_len: int) -> str:
    if value is None:
        return ""
    s = str(value)
    return s[:max_len]


def _resolve_company(subdomain: str | None) -> Company | None:
    if not subdomain:
        return None
    return Company.objects.filter(subdomain=subdomain).first()


class ActivityBeaconView(APIView):
    """POST /api/activity/batch/ — accept one beacon payload.

    Contract (all fields optional except ``session_key``):

    .. code-block:: json

        {
          "session_key": "uuid",
          "user_agent": "Mozilla/…",
          "viewport_width": 1440,
          "viewport_height": 900,
          "company_subdomain": "datbaby",
          "focused_ms_delta": 30000,
          "idle_ms_delta": 0,
          "ended": false,
          "events": [
            {"kind":"page_view", "area":"recon.workbench", "path":"/recon/workbench"},
            {"kind":"heartbeat", "area":"recon.workbench", "duration_ms":30000},
            {"kind":"action", "action":"match", "area":"recon.workbench",
             "duration_ms":340, "meta":{"num_bank":3}}
          ]
        }

    Returns ``{"session_id": int, "accepted": N}``. Designed to be
    called via ``navigator.sendBeacon`` on unload as well, so we
    never make the client wait on a body larger than
    confirmation-of-receipt.
    """

    permission_classes = [permissions.IsAuthenticated]
    # Critical: this endpoint must be callable from beacon/unload
    # handlers where the browser can't wait for CSRF tokens. DRF's
    # TokenAuthentication in headers + sendBeacon with a JSON body
    # handles this cleanly (sendBeacon can't set headers, so the
    # beacon falls back to fetch-keepalive — the client code does
    # this).

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        session_key = _clean_str(data.get("session_key"), max_len=64).strip()
        if not session_key:
            return Response(
                {"detail": "session_key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        events = data.get("events") or []
        if not isinstance(events, list):
            events = []
        if len(events) > _MAX_EVENTS_PER_BATCH:
            events = events[:_MAX_EVENTS_PER_BATCH]

        user = request.user
        company = _resolve_company(data.get("company_subdomain"))
        now = timezone.now()

        with db_transaction.atomic():
            session, created = UserActivitySession.objects.get_or_create(
                session_key=session_key,
                defaults={
                    "user": user,
                    "company": company,
                    "user_agent": _clean_str(data.get("user_agent"), max_len=512),
                    "viewport_width": _clean_int(data.get("viewport_width")),
                    "viewport_height": _clean_int(data.get("viewport_height")),
                },
            )

            # Anti-hijack: a second user POSTing with someone else's
            # session_key would otherwise silently piggyback. If the
            # row already exists under a different user, treat this
            # as a new session — mint a derived key.
            if not created and session.user_id != user.id:
                session = UserActivitySession.objects.create(
                    session_key=f"{session_key}:{user.id}",
                    user=user,
                    company=company,
                    user_agent=_clean_str(data.get("user_agent"), max_len=512),
                    viewport_width=_clean_int(data.get("viewport_width")),
                    viewport_height=_clean_int(data.get("viewport_height")),
                )

            # Accumulate timing deltas. ``focused_ms_delta`` is the
            # chunk of focused time since the last beacon; the client
            # is trusted to not send wildly inflated numbers (we cap
            # at 10 minutes per beacon to limit damage if it does).
            f_delta = min(_clean_int(data.get("focused_ms_delta")) or 0, 10 * 60_000)
            i_delta = min(_clean_int(data.get("idle_ms_delta")) or 0, 10 * 60_000)
            session.focused_ms = (session.focused_ms or 0) + f_delta
            session.idle_ms = (session.idle_ms or 0) + i_delta
            session.last_heartbeat_at = now
            if data.get("ended"):
                session.ended_at = now
            session.save(update_fields=[
                "focused_ms", "idle_ms", "last_heartbeat_at", "ended_at",
            ])

            # Bulk-insert events. We denormalise user+company at the
            # event level so dashboards don't join back through the
            # session table.
            objs = []
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                kind = _clean_str(ev.get("kind"), max_len=16)
                if kind not in _ALLOWED_KINDS:
                    continue
                objs.append(
                    UserActivityEvent(
                        session=session,
                        user=user,
                        company=company,
                        kind=kind,
                        area=_clean_str(ev.get("area"), max_len=64),
                        path=_clean_str(ev.get("path"), max_len=512),
                        action=_clean_str(ev.get("action"), max_len=64),
                        target_model=_clean_str(ev.get("target_model"), max_len=64),
                        target_id=_clean_str(ev.get("target_id"), max_len=64),
                        duration_ms=_clean_int(ev.get("duration_ms")),
                        meta=ev.get("meta") if isinstance(ev.get("meta"), (dict, list)) else None,
                    )
                )
            if objs:
                UserActivityEvent.objects.bulk_create(objs, batch_size=200)

            # For every ``kind=error`` event in the batch, upsert
            # an ErrorReport so the admin dashboard sees the group,
            # not just the individual occurrence. capture_error
            # also writes a second occurrence event with the full
            # stack + breadcrumbs attached — harmless duplication
            # with the bulk_create above because the report
            # aggregates on fingerprint either way.
            try:
                from core.models import ErrorReport
                from core.services.error_capture import (
                    capture_error,
                    fingerprint_frontend,
                )
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    if ev.get("kind") != UserActivityEvent.KIND_ERROR:
                        continue
                    meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
                    error_class = str(meta.get("error_class") or "Error")
                    message = str(meta.get("message") or "")
                    stack = str(meta.get("stack") or "")
                    breadcrumbs = meta.get("breadcrumbs") or []
                    fp = fingerprint_frontend(error_class, stack)
                    capture_error(
                        kind=ErrorReport.KIND_FRONTEND,
                        fingerprint=fp,
                        error_class=error_class,
                        message=message,
                        stack=stack,
                        path=_clean_str(ev.get("path"), max_len=512),
                        status_code=_clean_int(meta.get("status_code")),
                        method=_clean_str(meta.get("method"), max_len=8),
                        user=user,
                        company=company,
                        session=session,
                        breadcrumbs=breadcrumbs if isinstance(breadcrumbs, list) else None,
                        raw_meta={"ua": data.get("user_agent", "")[:200]} if data.get("user_agent") else None,
                    )
            except Exception:  # pragma: no cover — telemetry is best-effort
                pass

        return Response(
            {"session_id": session.id, "accepted": len(objs)},
            status=status.HTTP_200_OK,
        )


# --------------------------------------------------------------- admin reads


class AdminActivitySummaryView(APIView):
    """GET /api/admin/activity/summary/

    Platform-admin read: coarse time-per-area-per-user summary for
    the last ``days`` days (default 7). Keeps the payload compact —
    dashboards can drill into the raw events via
    ``AdminActivityEventsView`` below.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        try:
            days = int(request.query_params.get("days", "7"))
        except (TypeError, ValueError):
            days = 7
        days = max(1, min(days, 90))
        since = timezone.now() - timedelta(days=days)

        # Aggregate focused_ms from heartbeat events so the dashboard
        # can slice by user × area. Session-level sums are available
        # too but don't carry the per-area breakdown.
        from django.db.models import Count, Sum

        rows = (
            UserActivityEvent.objects
            .filter(created_at__gte=since, kind=UserActivityEvent.KIND_HEARTBEAT)
            .values("user_id", "user__username", "area")
            .annotate(
                total_ms=Sum("duration_ms"),
                events=Count("id"),
            )
            .order_by("-total_ms")
        )
        return Response({
            "since": since.isoformat(),
            "days": days,
            "rows": list(rows),
        })


class AdminActivityEventsView(APIView):
    """GET /api/admin/activity/events/?user=&area=&kind=&limit=

    Flat read of raw events — for per-user timelines and area
    drill-downs. Capped at 500 rows per request; paginate by
    ``before_id`` if the dashboard needs older rows.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        qs = UserActivityEvent.objects.all().select_related("user", "company").order_by("-id")
        for key, field in (("user", "user_id"), ("area", "area"), ("kind", "kind"), ("company", "company_id")):
            val = request.query_params.get(key)
            if val:
                qs = qs.filter(**{field: val})
        before = request.query_params.get("before_id")
        if before:
            try:
                qs = qs.filter(id__lt=int(before))
            except (TypeError, ValueError):
                pass
        try:
            limit = int(request.query_params.get("limit", "100"))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 500))
        events = list(qs[:limit].values(
            "id", "created_at", "user_id", "user__username", "company_id",
            "kind", "area", "path", "action", "target_model", "target_id",
            "duration_ms", "meta",
        ))
        return Response({"events": events, "count": len(events)})


class AdminActivityUserDetailView(APIView):
    """GET /api/admin/activity/users/<user_id>/?days=30

    Deeper per-user breakdown that the timeline page consumes in a
    single request. Returns:

      * ``totals``: overall focused_ms + events count
      * ``by_day``: [{date, focused_ms, events}] for the window
      * ``by_area``: [{area, focused_ms, events}] sorted by time
      * ``devices``: distinct user-agents seen, with last-seen
      * ``recent_actions``: last N action/search events (no heartbeats)
      * ``recent_errors``: last N errors
    """

    permission_classes = [IsSuperUser]

    def get(self, request, user_id, *args, **kwargs):
        try:
            days = int(request.query_params.get("days", "30"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        since = timezone.now() - timedelta(days=days)

        from django.contrib.auth import get_user_model
        from django.db.models import Count, Max, Sum
        from django.db.models.functions import TruncDate

        User = get_user_model()
        user = User.objects.filter(pk=user_id).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        ev = UserActivityEvent.objects.filter(user_id=user_id, created_at__gte=since)
        hb = ev.filter(kind=UserActivityEvent.KIND_HEARTBEAT)

        totals = hb.aggregate(focused_ms=Sum("duration_ms"), events=Count("id"))
        by_day = list(
            hb.annotate(date=TruncDate("created_at"))
              .values("date")
              .annotate(focused_ms=Sum("duration_ms"), events=Count("id"))
              .order_by("date")
        )
        by_area = list(
            hb.values("area")
              .annotate(focused_ms=Sum("duration_ms"), events=Count("id"))
              .order_by("-focused_ms")
        )
        devices = list(
            UserActivitySession.objects
              .filter(user_id=user_id, started_at__gte=since)
              .values("user_agent", "viewport_width", "viewport_height")
              .annotate(last_seen=Max("last_heartbeat_at"), sessions=Count("id"))
              .order_by("-last_seen")
        )
        recent_actions = list(
            ev.filter(kind__in=[UserActivityEvent.KIND_ACTION, UserActivityEvent.KIND_SEARCH])
              .order_by("-id")[:40]
              .values("id", "created_at", "kind", "area", "path", "action",
                      "target_model", "target_id", "duration_ms", "meta")
        )
        recent_errors = list(
            ev.filter(kind=UserActivityEvent.KIND_ERROR)
              .order_by("-id")[:25]
              .values("id", "created_at", "area", "path", "meta")
        )

        return Response({
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_superuser": user.is_superuser,
            },
            "since": since.isoformat(),
            "days": days,
            "totals": totals,
            "by_day": by_day,
            "by_area": by_area,
            "devices": devices,
            "recent_actions": recent_actions,
            "recent_errors": recent_errors,
        })


class AdminErrorReportsView(APIView):
    """GET /api/admin/activity/errors/?kind=&resolved=&days=&limit=

    Paginated list of error groups, newest-last-seen first by default
    (or most-frequent if ``order=count``). Filters:

      * ``kind``     — ``frontend``/``backend_drf``/``backend_django``/``celery``
      * ``resolved`` — ``true``/``false``/``any``   (default: ``false``)
      * ``days``     — 1..90 (last-seen within)
      * ``order``    — ``last_seen`` (default) or ``count``
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        from core.models import ErrorReport

        qs = ErrorReport.objects.all()

        kind = request.query_params.get("kind")
        if kind in dict(ErrorReport.KIND_CHOICES):
            qs = qs.filter(kind=kind)

        resolved = (request.query_params.get("resolved") or "false").lower()
        if resolved == "true":
            qs = qs.filter(is_resolved=True)
        elif resolved == "false":
            qs = qs.filter(is_resolved=False)
        # "any" → no filter

        try:
            days = int(request.query_params.get("days", "30"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        qs = qs.filter(last_seen_at__gte=timezone.now() - timedelta(days=days))

        order = request.query_params.get("order", "last_seen")
        qs = qs.order_by("-count" if order == "count" else "-last_seen_at")

        try:
            limit = int(request.query_params.get("limit", "100"))
        except (TypeError, ValueError):
            limit = 100
        limit = max(1, min(limit, 300))

        rows = list(qs[:limit].values(
            "id", "fingerprint", "kind", "error_class", "message",
            "path", "method", "status_code",
            "count", "affected_users",
            "first_seen_at", "last_seen_at",
            "is_resolved", "is_reopened", "resolved_at", "resolution_note",
        ))
        return Response({"days": days, "count": len(rows), "errors": rows})


class AdminErrorReportDetailView(APIView):
    """GET /api/admin/activity/errors/<id>/

    Deep view: the group row + a sample of the most recent occurrences
    with their breadcrumbs (last 20 events before each), plus per-user
    occurrence counts.

    POST toggles resolution: ``{"resolved": true, "note": "..."}``.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, report_id, *args, **kwargs):
        from core.models import ErrorReport, UserActivityEvent
        from django.db.models import Count

        report = ErrorReport.objects.filter(pk=report_id).first()
        if not report:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        occurrences_qs = (
            UserActivityEvent.objects
            .filter(kind=UserActivityEvent.KIND_ERROR,
                    meta__fingerprint=report.fingerprint)
            .select_related("user")
            .order_by("-id")
        )
        recent = list(
            occurrences_qs[:10].values(
                "id", "created_at", "user_id", "user__username", "path", "meta"
            )
        )
        by_user = list(
            occurrences_qs.values("user_id", "user__username")
                          .annotate(n=Count("id"))
                          .order_by("-n")[:20]
        )

        return Response({
            "report": {
                "id": report.id,
                "fingerprint": report.fingerprint,
                "kind": report.kind,
                "error_class": report.error_class,
                "message": report.message,
                "sample_stack": report.sample_stack,
                "path": report.path,
                "method": report.method,
                "status_code": report.status_code,
                "count": report.count,
                "affected_users": report.affected_users,
                "first_seen_at": report.first_seen_at,
                "last_seen_at": report.last_seen_at,
                "is_resolved": report.is_resolved,
                "is_reopened": report.is_reopened,
                "resolved_at": report.resolved_at,
                "resolution_note": report.resolution_note,
            },
            "recent_occurrences": recent,
            "by_user": by_user,
        })

    def post(self, request, report_id, *args, **kwargs):
        """Toggle resolution. Body: ``{"resolved": bool, "note": str}``.

        Setting ``resolved=True`` stamps ``resolved_by`` + ``resolved_at``
        and clears the ``is_reopened`` flag. Setting it back to False
        reopens the issue without touching history.
        """
        from core.models import ErrorReport

        report = ErrorReport.objects.filter(pk=report_id).first()
        if not report:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        body = request.data or {}
        resolved = bool(body.get("resolved"))
        note = str(body.get("note") or "")[:2000]

        report.is_resolved = resolved
        report.resolution_note = note
        if resolved:
            report.resolved_at = timezone.now()
            report.resolved_by = request.user
            report.is_reopened = False
        else:
            report.resolved_at = None
            report.resolved_by = None
            report.is_reopened = False
        report.save()
        return Response({
            "id": report.id,
            "is_resolved": report.is_resolved,
            "is_reopened": report.is_reopened,
            "resolved_at": report.resolved_at,
            "resolution_note": report.resolution_note,
        })


class AdminActivityDigestRunView(APIView):
    """POST /api/admin/activity/digest/run/

    On-demand trigger for the weekly digest. Body accepts:

    .. code-block:: json

      { "days": 7, "dry_run": false, "to": "override@example.com" }

    When ``dry_run=true``, the task returns the xlsx byte-count and
    subject without actually sending — used by the "Gerar prévia"
    button in the admin UI. The normal scheduled path goes through
    Celery Beat; this endpoint short-circuits for the "send it to me
    now" case.
    """

    permission_classes = [IsSuperUser]

    def post(self, request, *args, **kwargs):
        from core.tasks_activity_digest import send_weekly_digest

        body = request.data or {}
        try:
            days = int(body.get("days", 7))
        except (TypeError, ValueError):
            days = 7
        days = max(1, min(days, 90))
        dry_run = bool(body.get("dry_run", False))
        to = body.get("to") or None

        # Run synchronously — the admin expects a result now, and the
        # scheduled path already covers the fire-and-forget case.
        result = send_weekly_digest.run(days=days, dry_run=dry_run, recipient=to)
        return Response(result)


class AdminActivityFunnelsView(APIView):
    """GET /api/admin/activity/funnels/?days=30

    Returns the full set of hardcoded funnels with per-step
    counts, drop-off %, and inter-step p50/p95 timings. The
    dashboard renders each funnel as a horizontal bar chart + the
    timing column.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        try:
            days = int(request.query_params.get("days", "30"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        from core.services.activity_funnels import compute_all_funnels
        return Response({
            "days": days,
            "since": (timezone.now() - timedelta(days=days)).isoformat(),
            "funnels": compute_all_funnels(days=days),
        })


class AdminActivityFrictionView(APIView):
    """GET /api/admin/activity/friction/?days=30

    Four friction signals in one payload — back-and-forth
    navigation, long-dwell-no-action sessions, repeat-error
    chains, slow actions (p95 duration_ms). Heuristic-only.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        try:
            days = int(request.query_params.get("days", "30"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        from core.services.activity_friction import compute_friction
        payload = compute_friction(days=days)
        payload["since"] = (timezone.now() - timedelta(days=days)).isoformat()
        return Response(payload)


class AdminActivityAreaDetailView(APIView):
    """GET /api/admin/activity/areas/<area>/?days=30

    Per-area "what happens on this page?" report. Returns top users
    by time, top action labels, and a recent-activity sample so the
    admin can see what's actually being done there.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, area, *args, **kwargs):
        try:
            days = int(request.query_params.get("days", "30"))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 90))
        since = timezone.now() - timedelta(days=days)

        from django.db.models import Count, Sum

        ev = UserActivityEvent.objects.filter(area=area, created_at__gte=since)
        hb = ev.filter(kind=UserActivityEvent.KIND_HEARTBEAT)

        totals = {
            "focused_ms": hb.aggregate(v=Sum("duration_ms"))["v"] or 0,
            "events": ev.count(),
            "distinct_users": ev.values("user_id").distinct().count(),
        }
        top_users = list(
            hb.values("user_id", "user__username")
              .annotate(focused_ms=Sum("duration_ms"), events=Count("id"))
              .order_by("-focused_ms")[:20]
        )
        top_actions = list(
            ev.filter(kind=UserActivityEvent.KIND_ACTION)
              .exclude(action="")
              .values("action")
              .annotate(events=Count("id"), avg_duration_ms=Count("duration_ms"))
              .order_by("-events")[:20]
        )
        recent = list(
            ev.exclude(kind=UserActivityEvent.KIND_HEARTBEAT)
              .select_related("user")
              .order_by("-id")[:50]
              .values("id", "created_at", "user_id", "user__username", "kind",
                      "action", "path", "duration_ms", "meta")
        )

        return Response({
            "area": area,
            "since": since.isoformat(),
            "days": days,
            "totals": totals,
            "top_users": top_users,
            "top_actions": top_actions,
            "recent": recent,
        })
