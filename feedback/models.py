"""
Feedback models for capturing user supervision.

These models record user judgments on document types, spans, event codes and
search results.  The data collected here can be used to train better
classifiers and ranking models.
"""
from django.db import models

from npl.models import Document, Span, CourtEvent


class JudgmentSession(models.Model):
    """A session groups a set of feedback interactions by a user."""
    id = models.BigAutoField(primary_key=True)
    user_identifier = models.CharField(max_length=64)  # store hashed user or username
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    description = models.CharField(max_length=255, blank=True, default='')


class CandidateSet(models.Model):
    """A set of candidates presented to the user for a particular task."""
    TASK_CHOICES = [
        ('doctype', 'Document Type'),
        ('span', 'Span'),
        ('ecode', 'Event Code'),
        ('search', 'Search Results'),
    ]
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(JudgmentSession, on_delete=models.CASCADE)
    task_type = models.CharField(max_length=16, choices=TASK_CHOICES)
    reference_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Candidate(models.Model):
    """Represents an individual candidate item for user judgment."""
    id = models.BigAutoField(primary_key=True)
    candidate_set = models.ForeignKey(CandidateSet, related_name='candidates', on_delete=models.CASCADE)
    object_type = models.CharField(max_length=16)  # 'document', 'span', 'event', 'search'
    object_id = models.IntegerField()
    rank = models.IntegerField(default=0)
    suggested_value = models.JSONField(default=dict, blank=True)


class UserJudgment(models.Model):
    """Stores the outcome of a user's decision about a candidate."""
    id = models.BigAutoField(primary_key=True)
    candidate = models.ForeignKey(Candidate, related_name='judgments', on_delete=models.CASCADE)
    accepted = models.BooleanField(default=True)
    edited_value = models.JSONField(null=True, blank=True)
    order = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RetrieverRun(models.Model):
    """Records a retrieval run for search evaluation."""
    id = models.BigAutoField(primary_key=True)
    run_type = models.CharField(max_length=32)  # e.g. 'hybrid'
    parameters = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ModelVersion(models.Model):
    """Tracks versions of trained models and rules."""
    id = models.BigAutoField(primary_key=True)
    task = models.CharField(max_length=32)  # 'doctype', 'span', 'ecode', 'search'
    version_name = models.CharField(max_length=64)
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)