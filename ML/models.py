from django.db import models

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
