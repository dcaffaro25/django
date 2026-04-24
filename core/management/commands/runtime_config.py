"""Show what THIS running process actually picked up from its environment.

Useful when the Railway dashboard and ``railway.json`` might have
drifted, or to confirm that a deploy actually re-read a settings
change. Prints three independent views:

1. **Process** — the raw argv that started this (Linux ``/proc/<pid>/cmdline``),
   environment variables that matter (redacted for secrets), Python +
   Django + Celery versions.
2. **Django settings snapshot** — curated list of settings that
   actually impact prod behavior (TIME_ZONE, DEBUG, ALLOWED_HOSTS,
   DATABASES aliases, the Celery knobs, timeouts).
3. **Celery** — the effective ``app.conf`` the worker/beat process
   loaded, plus remote inspection of OTHER live workers via
   ``app.control.inspect()`` — which queues each worker subscribes
   to, how many pool processes, when they started.

Run it anywhere (local, dev shell on Railway web/worker/beat) to
get that process's view. Nothing mutates state.

Usage::

    python manage.py runtime_config                # this process only
    python manage.py runtime_config --workers      # add remote workers
    python manage.py runtime_config --json         # for tooling
    python manage.py runtime_config --all          # everything, verbose
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

from django.core.management.base import BaseCommand


# Env var keys we'll include verbatim (not secrets). Anything else
# matching ``*_KEY`` / ``*_SECRET`` / ``*_TOKEN`` / ``*_PASSWORD`` is
# masked. REDIS_URL and DATABASE_URL are partially masked to keep
# the host but hide credentials.
_SAFE_ENV_KEYS = {
    "DJANGO_SETTINGS_MODULE",
    "PYTHONUNBUFFERED",
    "PORT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_PROJECT_NAME",
    "CELERY_TASK_TIME_LIMIT",
    "DEBUG",
    "TZ",
}

_SENSITIVE_PATTERNS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "API_KEY")


def _redact_env_value(key: str, value: str) -> str:
    if any(p in key.upper() for p in _SENSITIVE_PATTERNS):
        return "***"
    return value


def _redact_url(url: str) -> str:
    """Mask credentials in a URL but keep host/port/db so you can
    verify it's pointing at the right Redis/Postgres."""
    if not url or "://" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return url
        _creds, hostpart = rest.split("@", 1)
        return f"{scheme}://***@{hostpart}"
    except Exception:
        return "***"


class Command(BaseCommand):
    help = "Dump this process's runtime config (argv, settings, Celery conf)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit a single JSON document (for tooling / diffing).",
        )
        parser.add_argument(
            "--workers",
            action="store_true",
            help="Also query live Celery workers via remote inspect.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Shorthand for --workers plus verbose sections.",
        )

    def handle(self, *args, **options):
        if options["all"]:
            options["workers"] = True

        report: Dict[str, Any] = {
            "process": _collect_process_info(),
            "django": _collect_django_info(),
            "celery_local": _collect_celery_local_info(),
            "beat_schedule": _collect_beat_schedule(),
        }
        if options["workers"]:
            report["celery_workers"] = _collect_celery_workers_info()

        if options["as_json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
            return

        _render_human(self.stdout, report, verbose=options["all"])


# --- collectors ------------------------------------------------------------


def _collect_process_info() -> Dict[str, Any]:
    import django

    info: Dict[str, Any] = {
        "pid": os.getpid(),
        "hostname": _safe_hostname(),
        "python_version": sys.version.split()[0],
        "django_version": django.get_version(),
        "argv": list(sys.argv),
        "executable": sys.executable,
    }

    # Parent process argv — tells us the actual gunicorn/celery
    # command when we're a worker child. Only works on Linux (/proc);
    # on Windows dev this quietly returns None.
    parent_cmdline = _read_parent_cmdline()
    if parent_cmdline is not None:
        info["parent_argv"] = parent_cmdline

    # Celery version, if installed.
    try:
        import celery
        info["celery_version"] = celery.__version__
    except Exception:  # pragma: no cover
        info["celery_version"] = None

    # Curated env (safe keys + redacted URLs).
    env: Dict[str, str] = {}
    for key in sorted(os.environ):
        val = os.environ[key]
        if key in _SAFE_ENV_KEYS:
            env[key] = val
        elif key.endswith("_URL") and "://" in val:
            env[key] = _redact_url(val)
        elif any(p in key.upper() for p in _SENSITIVE_PATTERNS):
            # Skip entirely; the redacted placeholder would just add noise.
            continue
    info["env"] = env
    return info


def _safe_hostname() -> str:
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return "unknown"


def _read_parent_cmdline() -> Optional[List[str]]:
    """Return the parent process's argv as a list, or None on Windows
    / permission errors. Uses /proc/<ppid>/cmdline."""
    try:
        ppid = os.getppid()
    except Exception:
        return None
    proc_path = f"/proc/{ppid}/cmdline"
    if not os.path.exists(proc_path):
        return None
    try:
        with open(proc_path, "rb") as f:
            raw = f.read()
        # cmdline is NUL-separated, with trailing NUL.
        parts = raw.split(b"\x00")
        return [p.decode("utf-8", errors="replace") for p in parts if p]
    except Exception:  # pragma: no cover
        return None


def _collect_django_info() -> Dict[str, Any]:
    from django.conf import settings

    # Database aliases with engine + host/name visible, credentials redacted.
    databases = {}
    for alias, cfg in (getattr(settings, "DATABASES", {}) or {}).items():
        databases[alias] = {
            "ENGINE": cfg.get("ENGINE"),
            "NAME": cfg.get("NAME"),
            "HOST": cfg.get("HOST"),
            "PORT": cfg.get("PORT"),
            # USER, PASSWORD deliberately omitted.
        }

    return {
        "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE"),
        "DEBUG": bool(getattr(settings, "DEBUG", False)),
        "ALLOWED_HOSTS": list(getattr(settings, "ALLOWED_HOSTS", []) or []),
        "TIME_ZONE": getattr(settings, "TIME_ZONE", None),
        "USE_TZ": getattr(settings, "USE_TZ", None),
        "LANGUAGE_CODE": getattr(settings, "LANGUAGE_CODE", None),
        "DATABASES": databases,
        # Celery-facing settings that override the app.conf defaults:
        "CELERY_BROKER_URL": _redact_url(getattr(settings, "CELERY_BROKER_URL", "")),
        "CELERY_RESULT_BACKEND": _redact_url(getattr(settings, "CELERY_RESULT_BACKEND", "")),
        "CELERY_TASK_TIME_LIMIT": getattr(settings, "CELERY_TASK_TIME_LIMIT", None),
        "CELERY_TASK_SOFT_TIME_LIMIT": getattr(settings, "CELERY_TASK_SOFT_TIME_LIMIT", None),
        "CELERY_TASK_ALWAYS_EAGER": bool(
            getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
        ),
    }


def _collect_celery_local_info() -> Dict[str, Any]:
    """Dump what THIS process sees in its local celery app.conf.

    Only interesting fields — the whole conf has ~200 keys. If you
    need everything, use ``celery -A nord_backend inspect conf`` on
    a worker.
    """
    try:
        from nord_backend.celery import app as celery_app
    except Exception as exc:
        return {"error": f"failed to import celery app: {exc}"}

    conf = celery_app.conf
    fields = [
        "task_acks_late",
        "task_reject_on_worker_lost",
        "worker_prefetch_multiplier",
        "worker_max_tasks_per_child",
        "worker_send_task_events",
        "task_send_sent_event",
        "task_track_started",
        "task_time_limit",
        "task_soft_time_limit",
        "broker_connection_retry_on_startup",
        "broker_transport_options",
        "task_default_queue",
        "task_serializer",
        "result_serializer",
        "accept_content",
        "timezone",
    ]
    out: Dict[str, Any] = {}
    for f in fields:
        try:
            out[f] = conf.get(f)
        except Exception:  # pragma: no cover
            out[f] = None
    # Redacted broker / result backend URLs for cross-ref with the
    # settings section.
    out["broker_url"] = _redact_url(conf.get("broker_url", ""))
    out["result_backend"] = _redact_url(conf.get("result_backend", ""))
    return out


def _collect_beat_schedule() -> Dict[str, Any]:
    """Snapshot of what Beat would schedule if it's running.

    This is the DEFINITION only — it doesn't say whether a beat
    process is actually alive. Pair with ``celery_queue_stats`` and
    the stale-session count to tell if beat is firing.
    """
    from django.conf import settings

    schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    out: Dict[str, Any] = {}
    for name, entry in schedule.items():
        out[name] = {
            "task": entry.get("task"),
            "schedule": str(entry.get("schedule")),
            "options": entry.get("options"),
            "kwargs": entry.get("kwargs"),
        }
    return out


def _collect_celery_workers_info() -> Dict[str, Any]:
    """Remote-inspect every live worker: its argv, its queues, its
    pool stats. Answers 'is the worker really running with
    -Q celery,recon_legacy,recon_fast --autoscale=20,4?'.
    """
    try:
        from nord_backend.celery import app as celery_app
    except Exception as exc:
        return {"error": f"celery app import: {exc}"}

    result: Dict[str, Any] = {"workers": {}, "warnings": []}
    try:
        inspect = celery_app.control.inspect(timeout=3.0)
        # active_queues: {worker: [{name, routing_key, exchange, ...}, ...]}
        active_queues = inspect.active_queues() or {}
        # stats: {worker: {total, pool: {...}, broker: {...}, ...}}
        stats = inspect.stats() or {}
    except Exception as exc:
        result["warnings"].append(f"inspect call failed: {exc}")
        return result

    worker_names = set(active_queues) | set(stats)
    if not worker_names:
        result["warnings"].append(
            "no workers responded within timeout - either none running "
            "or broker connection is broken"
        )
        return result

    for name in sorted(worker_names):
        queues = active_queues.get(name, []) or []
        s = stats.get(name, {}) or {}
        pool = s.get("pool", {}) or {}
        result["workers"][name] = {
            "queues_subscribed": [q.get("name") for q in queues if isinstance(q, dict)],
            "pool_processes": pool.get("max-concurrency"),
            "pool_size_min": pool.get("min-concurrency"),
            "prefetch_count": s.get("prefetch_count"),
            "total_tasks": s.get("total"),
            "broker_connect_timeout": s.get("broker", {}).get("connect_timeout"),
            "rusage": s.get("rusage"),
            "uptime_seconds": s.get("uptime"),
        }
    return result


# --- renderer --------------------------------------------------------------


def _render_human(stdout, report: Dict[str, Any], *, verbose: bool) -> None:
    def h(label: str) -> None:
        stdout.write(f"\n=== {label} ===")

    proc = report["process"]
    h("Process")
    stdout.write(f"  pid={proc['pid']}  host={proc['hostname']}")
    stdout.write(f"  python={proc['python_version']}  django={proc['django_version']}")
    stdout.write(f"  celery={proc.get('celery_version')}")
    stdout.write(f"  argv={' '.join(proc['argv'])}")
    parent = proc.get("parent_argv")
    if parent:
        stdout.write(f"  parent_argv={' '.join(parent)}")
    else:
        stdout.write("  parent_argv=<unavailable on this OS>")

    env = proc.get("env") or {}
    if env:
        stdout.write("  env:")
        for k in sorted(env):
            stdout.write(f"    {k}={env[k]}")

    dj = report["django"]
    h("Django")
    stdout.write(f"  settings_module={dj['settings_module']}")
    stdout.write(f"  DEBUG={dj['DEBUG']}  TZ={dj['TIME_ZONE']}  USE_TZ={dj['USE_TZ']}")
    stdout.write(f"  ALLOWED_HOSTS={dj['ALLOWED_HOSTS']}")
    stdout.write(f"  CELERY_BROKER_URL={dj['CELERY_BROKER_URL']}")
    stdout.write(f"  CELERY_TASK_ALWAYS_EAGER={dj['CELERY_TASK_ALWAYS_EAGER']}")
    stdout.write(
        f"  CELERY_TASK_TIME_LIMIT={dj['CELERY_TASK_TIME_LIMIT']}s "
        f"(soft={dj['CELERY_TASK_SOFT_TIME_LIMIT']}s)"
    )
    if verbose:
        stdout.write("  DATABASES:")
        for alias, cfg in (dj.get("DATABASES") or {}).items():
            stdout.write(
                f"    {alias}: engine={cfg['ENGINE']} host={cfg['HOST']}:{cfg['PORT']} name={cfg['NAME']}"
            )

    cl = report["celery_local"]
    h("Celery (this process's app.conf)")
    if "error" in cl:
        stdout.write(f"  ! {cl['error']}")
    else:
        for k, v in cl.items():
            stdout.write(f"  {k}={v}")

    bs = report.get("beat_schedule") or {}
    h(f"Beat schedule definition ({len(bs)} entr{'y' if len(bs) == 1 else 'ies'})")
    for name, entry in bs.items():
        stdout.write(f"  {name}:")
        stdout.write(f"    task:     {entry['task']}")
        stdout.write(f"    schedule: {entry['schedule']}")
        if entry.get("options"):
            stdout.write(f"    options:  {entry['options']}")
        if entry.get("kwargs"):
            stdout.write(f"    kwargs:   {entry['kwargs']}")

    workers = report.get("celery_workers")
    if workers is not None:
        h("Celery workers (remote inspect)")
        if "error" in workers:
            stdout.write(f"  ! {workers['error']}")
        for name, info in (workers.get("workers") or {}).items():
            stdout.write(f"  * {name}")
            stdout.write(f"      queues:        {info.get('queues_subscribed')}")
            stdout.write(f"      pool_max:      {info.get('pool_processes')}")
            stdout.write(f"      prefetch:      {info.get('prefetch_count')}")
            stdout.write(f"      total_tasks:   {info.get('total_tasks')}")
            up = info.get("uptime_seconds")
            if up is not None:
                stdout.write(f"      uptime_s:      {up}")
        for w in (workers.get("warnings") or []):
            stdout.write(f"  ! {w}")

    stdout.write("")  # final newline
