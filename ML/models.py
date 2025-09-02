from django.db import models
from django.utils import timezone

class MLModel(models.Model):
    """
    A generic model that stores serialized machine‑learning models along with
    metadata about how they were trained and how they should be used.
    """
    company = models.ForeignKey(
        "multitenancy.Company",
        on_delete=models.CASCADE,
        related_name="ml_models"
    )
    name = models.CharField(max_length=100)  # e.g. "categorization", "journal"
    version = models.PositiveIntegerField(default=1)
    model_type = models.CharField(max_length=50)  # optional descriptor
    description = models.TextField(blank=True, null=True)
    trained_at = models.DateTimeField(auto_now_add=True)
    model_blob = models.BinaryField()

    # NEW: metadata fields
    training_fields = models.JSONField(blank=True, null=True)
    prediction_fields = models.JSONField(blank=True, null=True)
    records_per_account = models.PositiveIntegerField(
        null=True,
        help_text="Number of recent records used per account when training"
    )
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("company", "name", "version")
        ordering = ["-trained_at"]

    def __str__(self) -> str:
        return f"{self.company} | {self.name} v{self.version} ({self.trained_at:%Y-%m-%d})"


class MLTrainingTask(models.Model):
    """
    Track async ML training jobs.
    """
    task_id = models.CharField(max_length=255, unique=True)
    tenant_id = models.CharField(max_length=100, null=True, blank=True)
    company_id = models.IntegerField()
    model_name = models.CharField(max_length=50)
    parameters = models.JSONField()
    status = models.CharField(max_length=20, default="queued")  # queued, running, completed, failed
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    result = models.JSONField(null=True, blank=True)  # optional, store model info / error

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.model_name} [{self.status}]"
