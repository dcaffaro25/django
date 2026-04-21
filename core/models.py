import uuid
from django.db import models
from multitenancy.models import BaseModel, TenantAwareBaseModel
from datetime import datetime
from typing import List, Optional
from dateutil.rrule import rrulestr

# core/models.py
from django.db import models
from django.conf import settings
from .constants import STATE_MAP, ALL_STATES
from django.contrib.auth import get_user_model

User = get_user_model()

class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Celery identifiers
    task_id   = models.CharField(max_length=100, unique=True, db_index=True)
    task_name = models.CharField(max_length=255)
    queue     = models.CharField(max_length=100, null=True, blank=True)
    worker    = models.CharField(max_length=200, null=True, blank=True)

    # free-form kind
    kind      = models.CharField(max_length=64, default="other", db_index=True)

    tenant_id   = models.CharField(max_length=64, null=True, blank=True)
    created_by  = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    state     = models.CharField(max_length=16, choices=[(s, s) for s in ALL_STATES],
                                 default=STATE_MAP["PENDING"], db_index=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    enqueued_at = models.DateTimeField(null=True, blank=True)
    started_at  = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    eta         = models.DateTimeField(null=True, blank=True)
    expires     = models.DateTimeField(null=True, blank=True)
    retries     = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=0)
    priority    = models.IntegerField(null=True, blank=True)

    # progress
    total       = models.PositiveIntegerField(null=True, blank=True)
    done        = models.PositiveIntegerField(null=True, blank=True)
    by_category = models.JSONField(null=True, blank=True)

    # misc
    meta   = models.JSONField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    error  = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "-created_at"]),
            models.Index(fields=["kind", "-created_at"]),
            models.Index(fields=["tenant_id", "-created_at"]),
        ]

    @property
    def percent(self):
        if not self.total or self.done is None or self.total <= 0:
            return None
        return round(100.0 * min(self.done, self.total) / float(self.total), 1)
    
class ActionEvent(models.Model):
    LEVELS = [("info","info"),("warning","warning"),("error","error")]
    company_id     = models.IntegerField(db_index=True)
    actor          = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="action_events")
    verb           = models.CharField(max_length=64)   # e.g. "import.started", "import.finished", "bank_tx.created"
    target_app     = models.CharField(max_length=64, blank=True, default="")
    target_model   = models.CharField(max_length=64, blank=True, default="")
    target_id      = models.CharField(max_length=64, blank=True, default="")
    level          = models.CharField(max_length=16, choices=LEVELS, default="info", db_index=True)
    message        = models.TextField(blank=True, default="")
    meta           = models.JSONField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["company_id","-created_at"]),
            models.Index(fields=["level","-created_at"]),
            models.Index(fields=["verb","-created_at"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.verb} #{self.id}"


# ------------------------------------------------------------------
# User activity tracking (platform-admin visibility).
# Append-only, mirrors AIUsageLog's shape so the admin dashboards can
# use the same indexing + retention playbook (90-day raw + daily
# aggregates). Two-tier grain on purpose:
#
#   UserActivitySession  — one row per browser tab; updated in place
#                          on heartbeats so "time focused" is cheap
#                          to sum without a window function.
#   UserActivityEvent    — one row per discrete thing (page_view,
#                          heartbeat, action, error, search). Joins
#                          via ``session`` but carries denormalised
#                          user/company so per-user and per-area
#                          queries skip the join entirely.
# ------------------------------------------------------------------


class UserActivitySession(models.Model):
    """One browser tab's lifetime.

    ``session_key`` is a client-minted UUID per tab. The backend
    upserts on it: subsequent heartbeats from the same tab update
    ``last_heartbeat_at`` + accumulated focused/idle time rather
    than spawning new rows. ``ended_at`` stays null until the tab
    flushes an ``end`` beacon (on ``beforeunload``) — the absence
    of ``ended_at`` + a stale ``last_heartbeat_at`` is how reports
    detect "probably closed".

    Intentionally not tenant-scoped via FK cascade: ``company`` is
    the tenant the user *was* scoped to at session start (via the
    URL subdomain). Users moving between tenants mid-session is
    rare; if it happens we'll spawn a new session row on the next
    heartbeat's area change.
    """

    session_key = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_sessions",
    )
    company = models.ForeignKey(
        "multitenancy.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_heartbeat_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # Milliseconds the tab spent actually focused vs. idle. Updated
    # incrementally — the client sends the delta since the last
    # heartbeat, the server adds it here. This keeps "time spent"
    # queryable without replaying every heartbeat event.
    focused_ms = models.BigIntegerField(default=0)
    idle_ms = models.BigIntegerField(default=0)

    user_agent = models.CharField(max_length=512, blank=True, default="")
    viewport_width = models.PositiveIntegerField(null=True, blank=True)
    viewport_height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-started_at"]),
            models.Index(fields=["company", "-started_at"]),
        ]

    def __str__(self):
        return f"session:{self.session_key[:8]}..@{self.user_id}"


class UserActivityEvent(models.Model):
    """Discrete activity beacon.

    Denormalises ``user`` + ``company`` off the parent session so
    the common queries ("time user X spent in area Y today") stay
    a single-table scan. ``path`` is stored **normalised** —
    querystring stripped, integer IDs replaced with ``:id`` — so
    heatmaps don't double-count ``/reports/view/1`` vs.
    ``/reports/view/2``. ``area`` is the canonical taxonomy key
    (``recon.workbench``, ``accounting.transactions``) that the
    frontend's ``areas.ts`` map emits.
    """

    KIND_PAGE_VIEW = "page_view"
    KIND_HEARTBEAT = "heartbeat"
    KIND_ACTION = "action"
    KIND_ERROR = "error"
    KIND_SEARCH = "search"
    KIND_CHOICES = (
        (KIND_PAGE_VIEW, "page_view"),
        (KIND_HEARTBEAT, "heartbeat"),
        (KIND_ACTION, "action"),
        (KIND_ERROR, "error"),
        (KIND_SEARCH, "search"),
    )

    session = models.ForeignKey(
        UserActivitySession,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_events",
    )
    company = models.ForeignKey(
        "multitenancy.Company",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    kind = models.CharField(max_length=16, choices=KIND_CHOICES, db_index=True)
    area = models.CharField(max_length=64, db_index=True, blank=True, default="")
    path = models.CharField(max_length=512, blank=True, default="")

    # ``action`` narrows ``kind=action`` (e.g. "match", "export",
    # "save", "download_xlsx"). Free-form by design — we'd rather
    # discover new labels than gate them behind enum migrations.
    action = models.CharField(max_length=64, blank=True, default="")
    target_model = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")

    # For ``kind=action``, how long the action took (click → server
    # ack). For ``kind=heartbeat``, the chunk of focused time
    # represented by this event. Null for page_view / error.
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    meta = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["company", "-created_at"]),
            models.Index(fields=["area", "-created_at"]),
            models.Index(fields=["kind", "-created_at"]),
            models.Index(fields=["user", "area", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.kind}:{self.area or self.path} #{self.id}"


class ErrorReport(models.Model):
    """Grouped error — the "issue" in Sentry terms.

    Every ``UserActivityEvent(kind='error')`` also triggers an upsert
    here, keyed on a stable fingerprint (hash of error_class +
    top-of-stack for frontend, or endpoint+status for backend). The
    goal is to collapse a noisy storm ("500 occurrences of the same
    bug") into one actionable row with count + first/last seen +
    distinct affected users.

    Individual occurrences stay in ``UserActivityEvent``; we join
    back via ``fingerprint`` on the event's ``meta`` blob when we
    need breadcrumbs. That keeps writes append-only (the report row
    is the only mutable surface) and lets the raw event retention
    job prune old noise without losing the issue history.
    """

    KIND_FRONTEND = "frontend"
    KIND_BACKEND_DRF = "backend_drf"
    KIND_BACKEND_DJANGO = "backend_django"
    KIND_CELERY = "celery"
    KIND_CHOICES = (
        (KIND_FRONTEND, "frontend"),
        (KIND_BACKEND_DRF, "backend_drf"),
        (KIND_BACKEND_DJANGO, "backend_django"),
        (KIND_CELERY, "celery"),
    )

    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, db_index=True)

    error_class = models.CharField(max_length=128, blank=True, default="")
    message = models.TextField(blank=True, default="")
    # Truncated. Full stack can be reconstructed from the latest
    # occurrence event if we need it. Kept short here so the list
    # endpoint stays cheap.
    sample_stack = models.TextField(blank=True, default="")

    # For backend reports: endpoint + method + status make the
    # "same bug on different routes" case distinguishable. For
    # frontend: the path where the error first fired.
    path = models.CharField(max_length=512, blank=True, default="")
    method = models.CharField(max_length=8, blank=True, default="")
    status_code = models.PositiveIntegerField(null=True, blank=True)

    # Counts + timestamps are the key dashboard columns.
    count = models.PositiveIntegerField(default=0)
    affected_users = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Resolution tracking. ``resolved_at`` + a re-occurrence after
    # that timestamp → we flip ``is_reopened`` and alert. That's
    # the "deploy brought it back" story.
    is_resolved = models.BooleanField(default=False)
    is_reopened = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_errors",
    )
    resolution_note = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["kind", "-last_seen_at"]),
            models.Index(fields=["is_resolved", "-last_seen_at"]),
            models.Index(fields=["-count"]),
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"[{self.kind}] {self.error_class}: {self.message[:60]}"


def get_next_n_occurrences(rrule_str: str, dtstart: datetime, n: int, after: Optional[datetime] = None) -> List[datetime]:
    """
    Returns the next 'n' occurrences after the 'after' datetime.
    If 'after' is None, uses 'dtstart' as the reference point.
    """
    rule = rrulestr(rrule_str, dtstart=dtstart)
    reference_date = after or dtstart
    occurrences = []
    next_occurrence = rule.after(reference_date, inc=False)
    while next_occurrence and len(occurrences) < n:
        occurrences.append(next_occurrence)
        next_occurrence = rule.after(next_occurrence, inc=False)
    return occurrences
        
def get_previous_n_occurrences(rrule_str: str, dtstart: datetime, n: int, before: Optional[datetime] = None) -> List[datetime]:
    """
    Returns the previous 'n' occurrences before the 'before' datetime.
    If 'before' is None, uses the current datetime as the reference point.
    """
    rule = rrulestr(rrule_str, dtstart=dtstart)
    reference_date = before or datetime.now()
    occurrences = []
    previous_occurrence = rule.before(reference_date, inc=False)
    while previous_occurrence and len(occurrences) < n:
        occurrences.append(previous_occurrence)
        previous_occurrence = rule.before(previous_occurrence, inc=False)
    return occurrences

def get_occurrences_between(rrule_str: str, dtstart: datetime, start: datetime, end: datetime) -> List[datetime]:
    """
    Returns all occurrences between 'start' and 'end' datetimes.
    """
    rule = rrulestr(rrule_str, dtstart=dtstart)
    return list(rule.between(start, end, inc=True))

class FinancialIndex(BaseModel):
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    INDEX_TYPES = [
        ('inflation', 'Inflation Index'),
        ('currency', 'Currency Exchange Rate'),
        ('interest', 'Interest Rate'),
        ('custom', 'Custom Index'),
    ]
    
    INTERPOLATION_STRATEGIES = [
       ('error', 'Error if missing'),
       ('last_known', 'Use last known value'),
       ('linear', 'Linear interpolation'),
       ('step', 'Step (carry last value)'),
       ('cumulative_rate', 'Cumulative Interest Rate'),
   ]
   
    
    name = models.CharField(max_length=100)
    index_type = models.CharField(max_length=20, choices=INDEX_TYPES)
    code = models.CharField(max_length=20, unique=True)  # e.g., IPCA, IGPM, USD-BRL
    interpolation_strategy = models.CharField(max_length=30, choices=INTERPOLATION_STRATEGIES, default='error')
    description = models.TextField(null=True, blank=True)
    quote_frequency = models.CharField(
        max_length=20,
        choices=[('daily', 'Daily'), ('monthly', 'Monthly'), ('yearly', 'Yearly')],
        default='monthly',
        help_text="How frequently this index is typically quoted"
    )
    expected_quote_format = models.CharField(
        max_length=50,
        choices=[
            ('daily_rate', 'Daily Rate'),
            ('monthly_rate', 'Monthly Rate'),
            ('accumulated', 'Accumulated'),
            ('absolute', 'Absolute')
        ],
        default='monthly_rate',
        help_text="Defines how this index is quoted (e.g., rate or value)"
    )
    is_forecastable = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['erp_id']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class IndexQuote(BaseModel):
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    index = models.ForeignKey(FinancialIndex, on_delete=models.CASCADE, related_name='quotes')
    date = models.DateField()
    value = models.DecimalField(max_digits=20, decimal_places=8)  # Adjust decimal places as necessary

    class Meta:
        unique_together = ('index', 'date')
        ordering = ['index', 'date']
        indexes = [
            models.Index(fields=['index', 'date']),
            models.Index(fields=['erp_id']),
        ]

    def __str__(self):
        return f"{self.index.code} @ {self.date}: {self.value}"
    
class FinancialIndexQuoteForecast(models.Model):
    erp_id = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        db_index=True,
        help_text="Stable identifier from the client's ERP (Omie/codigo, etc.) for upsert and sync.",
    )
    index = models.ForeignKey(FinancialIndex, on_delete=models.CASCADE, related_name='forecast_quotes')
    date = models.DateField()
    estimated_value = models.DecimalField(max_digits=10, decimal_places=6)
    source = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        unique_together = ('index', 'date')
        ordering = ['index', 'date']
        verbose_name = 'Financial Index Quote Forecast'
        indexes = [
            models.Index(fields=['erp_id']),
        ]

    def __str__(self):
        return f"{self.index.code} (forecast) @ {self.date}: {self.estimated_value}"