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

class Job(TenantAwareBaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Celery identifiers
    task_id   = models.CharField(max_length=100, unique=True, db_index=True)
    task_name = models.CharField(max_length=255)
    queue     = models.CharField(max_length=100, null=True, blank=True)
    worker    = models.CharField(max_length=200, null=True, blank=True)

    # free-form kind
    kind      = models.CharField(max_length=64, default="other", db_index=True)


    state     = models.CharField(max_length=16, choices=[(s, s) for s in ALL_STATES],
                                 default=STATE_MAP["PENDING"], db_index=True)


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
            #models.Index(fields=["tenant_id", "-created_at"]),
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
    
    def __str__(self):
        return f"{self.name} ({self.code})"

class IndexQuote(BaseModel):
    index = models.ForeignKey(FinancialIndex, on_delete=models.CASCADE, related_name='quotes')
    date = models.DateField()
    value = models.DecimalField(max_digits=20, decimal_places=8)  # Adjust decimal places as necessary

    class Meta:
        unique_together = ('index', 'date')
        ordering = ['index', 'date']
        indexes = [
            models.Index(fields=['index', 'date']),
        ]

    def __str__(self):
        return f"{self.index.code} @ {self.date}: {self.value}"
    
class FinancialIndexQuoteForecast(models.Model):
    index = models.ForeignKey(FinancialIndex, on_delete=models.CASCADE, related_name='forecast_quotes')
    date = models.DateField()
    estimated_value = models.DecimalField(max_digits=10, decimal_places=6)
    source = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        unique_together = ('index', 'date')
        ordering = ['index', 'date']
        verbose_name = 'Financial Index Quote Forecast'

    def __str__(self):
        return f"{self.index.code} (forecast) @ {self.date}: {self.estimated_value}"