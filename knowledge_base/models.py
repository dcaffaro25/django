"""
Knowledge Base models for NotebookLM-like document Q&A functionality.

This module provides models for managing knowledge bases, documents, answers,
and user feedback using Google's Gemini File Search Store API.
"""
import uuid
from django.db import models
from django.core.exceptions import ValidationError
from multitenancy.models import TenantAwareBaseModel, BaseModel
from npl.models import Document as NPLDocument


class KnowledgeBase(TenantAwareBaseModel):
    """
    A knowledge base maps to one Gemini File Search Store.
    Each tenant can have multiple knowledge bases.
    """
    name = models.CharField(max_length=255, help_text="Display name for the knowledge base")
    gemini_store_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Gemini File Search Store resource name (globally unique)"
    )
    
    class Meta:
        verbose_name = "Knowledge Base"
        verbose_name_plural = "Knowledge Bases"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.company.name})"
    
    def save(self, *args, **kwargs):
        # Generate unique store name if not provided
        if not self.gemini_store_name:
            self.gemini_store_name = f"kb_{self.company_id}_{uuid.uuid4().hex[:16]}"
        super().save(*args, **kwargs)


class KnowledgeDocument(TenantAwareBaseModel):
    """
    Represents a document in a knowledge base.
    Tracks indexing status and mapping to Gemini File Search Store.
    """
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('indexing', 'Indexing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    source_document = models.ForeignKey(
        NPLDocument,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='knowledge_documents',
        help_text="Optional reference to existing npl.Document"
    )
    filename = models.CharField(max_length=255, help_text="Original filename")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='queued',
        db_index=True
    )
    error = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if status is 'failed'"
    )
    gemini_doc_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Gemini File Search document resource name"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom metadata: file size, mime type, page count, etc."
    )
    
    class Meta:
        verbose_name = "Knowledge Document"
        verbose_name_plural = "Knowledge Documents"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['knowledge_base', 'status']),
        ]
    
    def __str__(self):
        return f"{self.filename} ({self.status})"
    
    def clean(self):
        """Ensure source_document belongs to same company if provided."""
        if self.source_document and hasattr(self.source_document, 'company'):
            if self.source_document.company != self.company:
                raise ValidationError("Source document must belong to the same company.")


class Answer(TenantAwareBaseModel):
    """
    Stores Q&A responses with citations and grounding metadata.
    """
    knowledge_base = models.ForeignKey(
        KnowledgeBase,
        on_delete=models.CASCADE,
        related_name='answers'
    )
    question = models.TextField(help_text="User's question")
    answer_text = models.TextField(help_text="Generated answer from Gemini")
    grounding_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw grounding metadata from Gemini API"
    )
    
    class Meta:
        verbose_name = "Answer"
        verbose_name_plural = "Answers"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Q: {self.question[:50]}..."


class AnswerFeedback(BaseModel):
    """
    User feedback on answers (thumbs up/down, comments, missing info flag).
    Not tenant-scoped (linked via Answer which is tenant-scoped).
    """
    RATING_CHOICES = [
        ('up', 'Thumbs Up'),
        ('down', 'Thumbs Down'),
    ]
    
    answer = models.ForeignKey(
        Answer,
        on_delete=models.CASCADE,
        related_name='feedback'
    )
    rating = models.CharField(
        max_length=10,
        choices=RATING_CHOICES,
        help_text="User rating: thumbs up or down"
    )
    comment = models.TextField(
        null=True,
        blank=True,
        help_text="Optional user comment"
    )
    missing_info = models.BooleanField(
        default=False,
        help_text="Flag if answer was missing important information"
    )
    
    class Meta:
        verbose_name = "Answer Feedback"
        verbose_name_plural = "Answer Feedback"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.rating} on Answer {self.answer_id}"
