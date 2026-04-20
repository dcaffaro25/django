"""Lightweight notifications feed for the topbar bell.

GET /{tenant}/api/notifications/?since=<ISO>&limit=<n>

Rather than introducing a new model + migration up front, we derive a live feed
from existing tenant-scoped activity in the last 7 days:

- ReconciliationTask state changes (completed / failed / cancelled)
- Reconciliation creations (approved/matched within window)
- Pending suggestions awaiting review

Each item gets a stable `key` so clients can dedupe / track "last seen". Unread
state is computed client-side (the frontend stores a per-user "last seen"
timestamp in localStorage and compares).

Response:
{
  "as_of": "2026-04-19T...",
  "items": [
    {"key": "task-123-completed", "type": "task_completed", "title": "...",
     "subtitle": "...", "created_at": "...", "url": "/recon/tasks?id=123"},
    ...
  ]
}
"""

from datetime import timedelta
from typing import Any, Dict, List

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.utils import resolve_tenant


class NotificationsView(APIView):
    """Derived notifications feed (no new DB tables)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, tenant_id=None):
        try:
            company = resolve_tenant(tenant_id)
            company_id = company.id
            subdomain = company.subdomain
        except Exception:
            return Response({"as_of": timezone.now().isoformat(), "items": []})

        try:
            limit = max(1, min(50, int(request.query_params.get("limit") or 20)))
        except (TypeError, ValueError):
            limit = 20

        since_str = request.query_params.get("since") or ""
        since_dt = parse_datetime(since_str) if since_str else None
        default_window = timezone.now() - timedelta(days=7)
        window = since_dt or default_window

        from accounting.models import Reconciliation, ReconciliationTask

        items: List[Dict[str, Any]] = []

        # Tasks with terminal states in the window (scoped by tenant_id subdomain)
        tasks = (
            ReconciliationTask.objects.filter(
                tenant_id=subdomain,
                updated_at__gte=window,
                status__in=["completed", "failed", "cancelled"],
            )
            .order_by("-updated_at")[:limit]
        )
        for t in tasks:
            name = t.config_name or t.pipeline_name or f"#{t.id}"
            # Completed tasks deep-link to the Sugestões page so the user
            # lands on the list of match candidates they can actually act
            # on; failed/cancelled runs still go to the Execuções page
            # where the error message lives.
            if t.status == "completed":
                url = f"/recon/suggestions?task_id={t.id}"
            else:
                url = f"/recon/tasks?id={t.id}"
            if t.status == "completed":
                total_bank = int(t.bank_candidates or 0)
                matched = int(t.matched_bank_transactions or 0)
                parts: List[str] = []
                if t.suggestion_count:
                    parts.append(f"{t.suggestion_count} sugestões")
                if matched:
                    parts.append(
                        f"{matched}/{total_bank} banco" if total_bank else f"{matched} banco"
                    )
                if t.auto_match_applied:
                    parts.append(f"{t.auto_match_applied} auto-aplicados")
                if t.duration_seconds:
                    parts.append(f"{t.duration_seconds:.0f}s")
                sub = " · ".join(parts) if parts else "Nenhuma sugestão gerada"
            elif t.status == "failed":
                sub = (t.error_message or "Erro na execução")[:120]
            else:
                sub = "Cancelado pelo usuário"
            items.append({
                "key": f"task-{t.id}-{t.status}",
                "type": f"task_{t.status}",
                "title": f"Execução {name} — {t.status}",
                "subtitle": sub,
                "created_at": t.updated_at.isoformat() if t.updated_at else None,
                "url": url,
            })

        # Reconciliations just matched/approved in the window
        matches = (
            Reconciliation.objects.filter(
                company_id=company_id,
                is_deleted=False,
                status__in=["matched", "approved"],
                updated_at__gte=window,
            )
            .order_by("-updated_at")[:limit]
        )
        for r in matches:
            items.append({
                "key": f"recon-{r.id}-{r.status}",
                "type": f"reconciliation_{r.status}",
                "title": f"Conciliação {r.status}",
                "subtitle": r.reference or f"#{r.id}",
                "created_at": r.updated_at.isoformat() if r.updated_at else None,
                "url": "/recon/workbench",
            })

        # Sort everything by created_at desc and cap
        items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        items = items[:limit]

        return Response({"as_of": timezone.now().isoformat(), "items": items})
