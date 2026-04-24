"""Celery app + global config.

Knob rationale (see ``settings.py`` for the time-limit values
themselves — those are env-tunable; everything here is broker-/
worker-level behaviour that doesn't belong in settings).

Deployed topology (see railway.json):
  * ``web``    — gunicorn, handles HTTP.
  * ``worker`` — ``celery -A nord_backend worker`` (1 service, N processes).
  * ``beat``   — ``celery -A nord_backend beat`` (exactly one instance —
                 multiple beats would duplicate every scheduled task).
"""
import os
from celery import Celery

# Default settings for Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nord_backend.settings")

app = Celery("nord_backend")

# Load settings from Django settings, prefixed with "CELERY_"
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py from all installed apps
app.autodiscover_tasks()


# --- broker / worker reliability knobs -------------------------------------
#
# Everything below was absent or incorrectly declared before the Phase
# 6.z-h audit (task-queue stuckness investigation). All of these are
# conservative defaults for a small-to-medium Celery deployment backed
# by a single Redis; they trade some throughput for not losing tasks
# on worker crashes.

app.conf.update(
    # Retry the initial broker connection when the worker boots —
    # without this, a transient Redis startup delay kills the worker
    # process. Was a free-floating module variable at the top of
    # this file before, which didn't take effect.
    broker_connection_retry_on_startup=True,

    # --- task acknowledgement ---------------------------------------------
    # ``acks_late=True`` means the worker ACKs the task AFTER it
    # finishes, not before it starts. Paired with
    # ``reject_on_worker_lost=True``, a SIGKILL'd worker (OOM, Railway
    # container restart, etc.) causes the task to be re-queued for
    # another worker instead of being silently lost.
    #
    # Tradeoff: tasks must be idempotent on re-run. For imports v2 the
    # status-gating in analyze_session_task / commit_session_task
    # handles that — both early-return if the session already left
    # its non-terminal status. For other tasks (send_email,
    # generate_missing_embeddings, etc.) re-run is harmless at
    # worst and redundant at common case.
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # --- fair scheduling --------------------------------------------------
    # Default prefetch is 4 per worker process — great for many short
    # tasks, terrible when one worker is busy with a long import and
    # the other is sitting idle with 4 reserved tasks it hasn't
    # touched. Setting to 1 makes the broker round-robin tasks to
    # whichever worker is free RIGHT NOW.
    #
    # Note: the production ``worker`` service in railway.json also
    # sets ``--prefetch-multiplier=1`` on the CLI. Both say 1, so
    # there's no conflict; keeping the config-level setting here for
    # dev (``celery worker`` invocations without the flag) and for
    # anyone running the worker outside Railway.
    worker_prefetch_multiplier=1,

    # --- recycle workers to contain memory leaks --------------------------
    # Long-running Python workers drift upward in memory thanks to
    # fragmentation + pandas/numpy caches from ETL imports. After
    # ``max_tasks_per_child`` tasks the worker process exits cleanly
    # and Celery spawns a fresh one. Pick a value high enough that
    # the fork overhead is amortised across lots of tasks.
    worker_max_tasks_per_child=200,

    # --- broker-level safety --------------------------------------------
    # ``visibility_timeout`` governs when Redis re-delivers an un-ACK'd
    # task to another consumer. Default is 1h; making it explicit so
    # nobody is surprised when a task that crashed silently gets
    # re-run an hour later.
    broker_transport_options={
        "visibility_timeout": 3600,
    },

    # --- observability ---------------------------------------------------
    # Already on before 6.z-h; keeping them set here so the whole
    # config is in one place.
    task_track_started=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
)
