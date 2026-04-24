"""Clear stuck tasks out of the Celery queue + reap stale v2 sessions.

Emergency tool for when ``celery_queue_stats`` shows a pile-up. Can:

1. **Purge the Redis queue** (--queue <name>): drops ALL pending
   tasks waiting for a worker. Use when the queue has filled with
   junk that can't be replayed safely.

2. **Revoke active tasks** (--revoke): tells running workers to
   terminate in-flight tasks. Pair with a ``--signal`` flag to pick
   SIGTERM (graceful) or SIGKILL (immediate). Tasks that were
   ACK'd-late (our default after 6.z-h) get re-queued to another
   worker; tasks ACK'd-early are lost.

3. **Reap stale v2 import sessions** (--reap-imports): runs the
   ``imports_v2.reap_stale_sessions`` logic synchronously. Useful
   if beat isn't running (on-call fire drill) and you need to
   clear stuck sessions right now.

Usage::

    # Inspect only (safe, same as celery_queue_stats).
    python manage.py celery_purge_stuck --dry-run

    # Kick stuck v2 import sessions to error.
    python manage.py celery_purge_stuck --reap-imports

    # Nuclear: clear the default queue AND revoke all active tasks.
    python manage.py celery_purge_stuck --queue celery --revoke

Always dry-run first. Tasks can't be un-purged once they're gone.
"""
from __future__ import annotations

import sys
from typing import Any, Dict

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Clear stuck Celery tasks / stale import sessions. Destructive — dry-run first."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without doing it.",
        )
        parser.add_argument(
            "--queue",
            action="append",
            default=None,
            help="Redis queue name(s) to purge. Pass multiple --queue flags "
                 "for additional queues. Default: no purge.",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke all currently-active tasks on all workers.",
        )
        parser.add_argument(
            "--signal",
            choices=("TERM", "KILL"),
            default="TERM",
            help="Signal to send when --revoke is used (default: TERM). "
                 "KILL is immediate but may leave partial state.",
        )
        parser.add_argument(
            "--reap-imports",
            action="store_true",
            help="Flip v2 ImportSession rows stuck in analyzing/committing "
                 "past the hard time limit to error (runs the same logic "
                 "Celery Beat schedules every 5 min).",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        did_anything = False

        if options["queue"]:
            did_anything = True
            self._purge_queues(options["queue"], dry=dry)

        if options["revoke"]:
            did_anything = True
            self._revoke_active(options["signal"], dry=dry)

        if options["reap_imports"]:
            did_anything = True
            self._reap_imports(dry=dry)

        if not did_anything:
            raise CommandError(
                "Nothing to do. Pass at least one of --queue, --revoke, "
                "or --reap-imports. Use --dry-run to preview."
            )

    # --- purge ------------------------------------------------------------

    def _purge_queues(self, queue_names, *, dry: bool) -> None:
        """Delete the Redis list backing each queue."""
        from nord_backend.celery import app as celery_app
        try:
            import redis
        except ImportError:
            raise CommandError("redis package not installed")

        client = redis.Redis.from_url(
            celery_app.conf.broker_url,
            socket_connect_timeout=2, socket_timeout=2,
        )
        for q in queue_names:
            depth = client.llen(q)
            prefix = "[dry-run] would delete" if dry else "deleting"
            self.stdout.write(
                self.style.WARNING(f"{prefix} {depth} message(s) from queue '{q}'")
            )
            if not dry and depth:
                client.delete(q)

    # --- revoke ----------------------------------------------------------

    def _revoke_active(self, signal: str, *, dry: bool) -> None:
        """Iterate workers, list active tasks, broadcast revoke+terminate.

        ``signal='TERM'`` gives the task a chance to clean up (SIGTERM);
        ``signal='KILL'`` is immediate. Either way, tasks running with
        ``acks_late=True`` (our default after 6.z-h) get re-queued for
        another worker — idempotent ones (imports_v2 analyze/commit
        with status gating) are safe.
        """
        from nord_backend.celery import app as celery_app
        inspect = celery_app.control.inspect(timeout=3.0)
        active_by_worker = inspect.active() or {}

        if not active_by_worker:
            self.stdout.write("no active tasks reported")
            return

        ids = []
        for worker, tasks in active_by_worker.items():
            for t in tasks or []:
                if isinstance(t, dict) and t.get("id"):
                    ids.append((worker, t["id"], t.get("name")))

        if not ids:
            self.stdout.write("no task ids found on active workers")
            return

        self.stdout.write(
            self.style.WARNING(
                f"{'[dry-run] would revoke' if dry else 'revoking'} "
                f"{len(ids)} active task(s) with SIG{signal}"
            )
        )
        for worker, tid, tname in ids:
            self.stdout.write(f"  - {tname} id={tid} on {worker}")

        if not dry:
            sig = f"SIG{signal}"
            for _, tid, _ in ids:
                celery_app.control.revoke(tid, terminate=True, signal=sig)

    # --- reap imports ----------------------------------------------------

    def _reap_imports(self, *, dry: bool) -> None:
        """Synchronously run the v2 stale-session reaper."""
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone
        from multitenancy.models import ImportSession

        hard_limit_s = int(
            getattr(settings, "CELERY_TASK_TIME_LIMIT", 1800) or 1800
        )
        cutoff = timezone.now() - timedelta(seconds=hard_limit_s + 60)
        non_terminal = [
            ImportSession.STATUS_ANALYZING,
            ImportSession.STATUS_COMMITTING,
        ]
        stale = ImportSession.objects.filter(
            status__in=non_terminal, updated_at__lt=cutoff,
        )
        pks = list(stale.values_list("pk", flat=True))

        self.stdout.write(
            self.style.WARNING(
                f"{'[dry-run] would reap' if dry else 'reaping'} {len(pks)} "
                f"session(s) older than {hard_limit_s + 60}s"
            )
        )
        if not pks:
            return
        for pk in pks[:20]:
            self.stdout.write(f"  - session #{pk}")
        if len(pks) > 20:
            self.stdout.write(f"  … and {len(pks) - 20} more")

        if not dry:
            # Reuse the Celery task's logic so we don't drift.
            from multitenancy.imports_v2.tasks import reap_stale_sessions_task
            result = reap_stale_sessions_task()
            self.stdout.write(
                self.style.SUCCESS(f"reaped {result.get('reaped', 0)} session(s)")
            )
