"""Manual trigger for the weekly activity digest.

Usage::

    python manage.py send_activity_digest           # send to the default recipient
    python manage.py send_activity_digest --dry-run # build xlsx, skip email, print stats
    python manage.py send_activity_digest --to=alice@example.com --days=14

Intentionally calls the Celery task in-process (synchronously) so the
operator gets an immediate result + exit code; there's no benefit to
going through the worker for a one-shot invocation.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.tasks_activity_digest import send_weekly_digest


class Command(BaseCommand):
    help = "Build + email the weekly activity digest. Defaults to the user 'dcaffaro'."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--days", type=int, default=7, help="Window length in days (default 7).")
        parser.add_argument("--to", type=str, default=None, help="Override recipient email.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Build the xlsx + compute stats, but do not send the email.")

    def handle(self, *args, **opts) -> None:
        result = send_weekly_digest.run(
            days=opts["days"],
            dry_run=opts["dry_run"],
            recipient=opts["to"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"digest result: {result}"
        ))
