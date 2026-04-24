"""Platform-admin endpoint for inspecting the running service's config.

Mirrors the ``runtime_config`` management command but over HTTP so
operators can verify their Railway deploy without shell access.

Output shape matches the command's ``--json`` mode (except with
``redis_queues`` added so the page can show queue depth too):

  * ``process`` — argv, pid, hostname, versions, curated env.
  * ``django`` — settings snapshot.
  * ``celery_local`` — the web service's view of ``app.conf``.
  * ``beat_schedule`` — what Beat would schedule (definition only).
  * ``celery_workers`` — remote inspect of live workers.
  * ``redis_queues`` — queue depths via LLEN.
  * ``stale_import_sessions`` — count + oldest pks.

Superuser-only; matches existing admin endpoints under
``/api/admin/*``.
"""
from __future__ import annotations

from typing import Any, Dict, List

from rest_framework.response import Response
from rest_framework.views import APIView

from multitenancy.permissions import IsSuperUser

# Reuse the collectors from the management command. Single source of
# truth so the HTTP payload and the CLI output can never drift.
from core.management.commands.runtime_config import (
    _collect_beat_schedule,
    _collect_celery_local_info,
    _collect_celery_workers_info,
    _collect_django_info,
    _collect_process_info,
)


class AdminRuntimeConfigView(APIView):
    """``GET /api/admin/runtime/``

    Returns a single JSON document describing what THIS service (the
    web process) picked up at boot, plus remote-inspect data from
    every live Celery worker.

    Optional query params:

      * ``?queue=celery&queue=recon_legacy`` — additional Redis queues
        to measure depth for. ``celery`` is always included.
      * ``?inspect_timeout=3`` — RPC timeout in seconds for the worker
        inspection (default 3).

    Typical call: the frontend ``/admin/runtime`` page issues a bare
    GET and renders whatever comes back.
    """

    permission_classes = [IsSuperUser]

    def get(self, request, *args, **kwargs):
        # Always include the default queue; operators can ask for more.
        queues: List[str] = ["celery"]
        for extra in request.GET.getlist("queue"):
            if extra and extra not in queues:
                queues.append(extra)

        try:
            inspect_timeout = float(
                request.GET.get("inspect_timeout", "3") or "3"
            )
        except (TypeError, ValueError):
            inspect_timeout = 3.0

        payload: Dict[str, Any] = {
            "process": _collect_process_info(),
            "django": _collect_django_info(),
            "celery_local": _collect_celery_local_info(),
            "beat_schedule": _collect_beat_schedule(),
            "celery_workers": _collect_celery_workers_info(),
            "redis_queues": _collect_redis_queue_depth(queues),
            "stale_import_sessions": _collect_stale_import_sessions(),
        }
        return Response(payload)


def _collect_redis_queue_depth(queue_names: List[str]) -> Dict[str, Any]:
    """LLEN each queue; redact the broker URL in the result."""
    result: Dict[str, Any] = {"depths": {}, "error": None}
    try:
        from nord_backend.celery import app as celery_app
        broker_url = celery_app.conf.broker_url
    except Exception as exc:  # pragma: no cover
        result["error"] = f"celery app: {exc}"
        return result

    try:
        import redis
        client = redis.Redis.from_url(
            broker_url, socket_connect_timeout=2, socket_timeout=2,
        )
        for q in queue_names:
            try:
                result["depths"][q] = client.llen(q)
            except Exception as exc:
                result["depths"][q] = None
                result["error"] = f"LLEN {q}: {exc}"
    except Exception as exc:
        result["error"] = f"redis unreachable: {exc}"
    return result


def _collect_stale_import_sessions() -> Dict[str, Any]:
    """Count of v2 ImportSession rows stuck in analyzing/committing
    past the Celery hard time limit. Mirrors the celery_queue_stats
    helper so the page and CLI agree.
    """
    from datetime import timedelta
    from django.conf import settings
    from django.utils import timezone
    try:
        from multitenancy.models import ImportSession
    except Exception as exc:  # pragma: no cover
        return {"count": None, "oldest_pks": [], "error": str(exc)}

    hard_limit_s = int(
        getattr(settings, "CELERY_TASK_TIME_LIMIT", 1800) or 1800
    )
    cutoff = timezone.now() - timedelta(seconds=hard_limit_s + 60)
    stuck = ImportSession.objects.filter(
        status__in=[
            ImportSession.STATUS_ANALYZING,
            ImportSession.STATUS_COMMITTING,
        ],
        updated_at__lt=cutoff,
    )
    return {
        "count": stuck.count(),
        "oldest_pks": list(
            stuck.order_by("updated_at").values_list("pk", flat=True)[:10]
        ),
        "hard_limit_seconds": hard_limit_s,
    }
