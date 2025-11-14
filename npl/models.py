"""
Database models for the NPL application.

These models represent legal documents, their extracted spans, events and
structured data derived from those documents.  The goal is to capture the
information necessary to power the full NPL pipeline described in the
requirements.  Fields are annotated with comments explaining their purpose.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models

from typing import Any, Dict, Iterable, List, Tuple, Optional
# Attempt to import the VectorField from pgvector.  If pgvector is not
# installed, fall back to a JSON field for storage.  Users can install
# ``pgvector`` to enable efficient similarity search.
try:
    from pgvector.django import VectorField  # type: ignore
except Exception:
    VectorField = None  # type: ignore

class DocTypeRule(models.Model):
    """
    Armazena regras de classificação de tipo documental.

    As âncoras de cada categoria (forte, fraca e negativa) são armazenadas em campos
    de texto, separadas por ';'. Por exemplo: "decido; defiro; julgo procedente".
    """
    doc_type = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)

    # Âncoras fortes: se qualquer âncora forte ocorrer no texto, classifica como este tipo.
    anchors_strong = models.TextField(
        blank=True,
        help_text="Âncoras fortes separadas por ';' (e.g. 'decido; defiro')",
    )

    # Âncoras fracas: indícios de que o documento pode ser deste tipo.
    anchors_weak = models.TextField(
        blank=True,
        help_text="Âncoras fracas separadas por ';'",
    )

    # Âncoras negativas: se alguma aparecer, este tipo é ignorado.
    anchors_negative = models.TextField(
        blank=True,
        help_text="Âncoras negativas separadas por ';'",
    )

    def __str__(self):
        return f"{self.doc_type} – {self.description}"


class Process(models.Model):
    """Represents a judicial process or case.

    All documents and events are associated with a process.  The ``tenant_id``
    field is used to isolate data across different tenants for multi‑tenant
    deployments.
    """

    id = models.BigAutoField(primary_key=True)
    case_number = models.CharField(max_length=64, unique=True)
    tenant_id = models.CharField(max_length=32, default='default')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.case_number


class EventType(models.Model):
    """Defines an event type (E‑code)."""

    code = models.CharField(max_length=8, primary_key=True)
    description = models.CharField(max_length=255)
    def __str__(self) -> str:
        return f"{self.code}: {self.description}"


class Document(models.Model):
    """
    Representa um documento enviado associado a um processo.

    O campo `process` é opcional no momento do upload; a tarefa de OCR tentará
    extrair o número do processo e criar/associar um processo posteriormente.
    """
    EMBEDDING_MODE_CHOICES = [
        ("all_paragraphs", "Todos os parágrafos"),
        ("spans_only", "Apenas spans"),
        ("none", "Sem embeddings"),
    ]
    
    id = models.BigAutoField(primary_key=True)

    # Processo associado, se houver; pode ser nulo até que o OCR encontre o número.
    process = models.ForeignKey(
        Process,
        related_name='documents',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="O processo associado, se conhecido."
    )

    # Número de processo cru extraído pelo OCR, antes de criar/vincular Process.
    process_number_raw = models.CharField(
        max_length=64,
        blank=True,
        default='',
        help_text="Número de processo extraído do texto (formato bruto)."
    )

    # Marca quando não foi possível detectar um número de processo.
    no_process_found = models.BooleanField(
        default=False,
        help_text="Verdadeiro se nenhum número de processo foi detectado."
    )

    # Demais campos do documento
    file = models.FileField(upload_to='documents/')
    mime_type = models.CharField(max_length=64, blank=True, default='')
    num_pages = models.IntegerField(default=0)
    text_hash = models.CharField(max_length=64, blank=True, default='')
    ocr_text = models.TextField(blank=True, default='')
    ocr_data = models.JSONField(default=dict, help_text="Resultados de OCR por página com metadados.")
    doc_type = models.CharField(max_length=64, blank=True, default='')
    doctype_confidence = models.FloatField(default=0.0)
    embedding_mode = models.CharField(
        max_length=20,
        choices=EMBEDDING_MODE_CHOICES,
        default="all_paragraphs",
        help_text="Define como os embeddings serão gerados para este documento."
    )
    processing_stats = models.JSONField(
        null=True, blank=True,
        help_text="Métricas de desempenho (tempo, contagem de parágrafos, spans etc.)"
    )
    rules_version = models.CharField(max_length=32, blank=True, default='v0')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self) -> str:
        return f"Document {self.id} (process {self.process_id})"

class SpanRule(models.Model):
    """
    Regras de extração de spans.

    - label: rótulo principal (ex.: 'PENHORA', 'FUNDAMENTACAO').
    - description: descrição amigável.
    - anchors_strong, anchors_weak, anchors_negative: listas de âncoras separadas por ';'.
    - embedding_model: nome do modelo usado nas similaridades (por enquanto, 'nomic').
    - anchor_embeddings: lista de vetores (um por âncora forte), armazenados como JSON.
    """

    label = models.CharField(max_length=64, unique=True)
    description = models.CharField(max_length=255, blank=True)
    
    doc_type = models.ForeignKey(DocTypeRule, related_name='span_rules', on_delete=models.CASCADE)
    
    anchors_strong = models.TextField(
        blank=True,
        help_text="Âncoras fortes separadas por ';' (e.g. 'converto a penhora; defiro a penhora')",
    )
    anchors_weak = models.TextField(
        blank=True,
        help_text="Âncoras fracas separadas por ';'",
    )
    anchors_negative = models.TextField(
        blank=True,
        help_text="Âncoras negativas separadas por ';'",
    )

    embedding_model = models.CharField(
        max_length=128,
        default="nomic-embed-text",
        help_text="Modelo de embedding usado nas similaridades (usar 'nomic' por padrão)",
    )
    # Salva o embedding de cada âncora forte; armazenado como lista de listas em JSON
    anchor_embeddings = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.label} – {self.description}"

    def strong_anchor_list(self) -> List[str]:
        return [a.strip() for a in self.anchors_strong.split(';') if a.strip()]

    def weak_anchor_list(self) -> List[str]:
        return [a.strip() for a in self.anchors_weak.split(';') if a.strip()]

    def negative_anchor_list(self) -> List[str]:
        return [a.strip() for a in self.anchors_negative.split(';') if a.strip()]

class Span(models.Model):
    """Represents a labelled span of text extracted from a document.

    Spans capture sections such as headers, reports, dispositives and other
    domain‑specific concepts.  The ``label`` field stores the primary label,
    while ``label_subtype`` can contain more granular categorization.  ``extra``
    allows arbitrary metadata to be attached to the span.
    """
    id = models.BigAutoField(primary_key=True)
    document = models.ForeignKey(Document, related_name='spans', on_delete=models.CASCADE)
    label = models.CharField(max_length=64)
    label_subtype = models.CharField(max_length=64, blank=True, default='')
    text = models.TextField()
    page = models.IntegerField(default=0)
    char_start = models.IntegerField(default=0)
    char_end = models.IntegerField(default=0)
    bbox = models.JSONField(null=True, blank=True)
    strong_anchor_count = models.IntegerField(default=0)
    weak_anchor_count = models.IntegerField(default=0)
    negative_anchor_count = models.IntegerField(default=0)
    anchors_pos = models.JSONField(null=True, blank=True)
    anchors_neg = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(default=0.0)
    extra = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"Span {self.label} (doc {self.document_id}, page {self.page})"


class SpanEmbedding(models.Model):
    """Stores dense vector embeddings for spans.

    Two models (DenseA and DenseB) can be configured via environment variables.
    ``vector`` uses ``pgvector`` when available.  If ``pgvector`` is not
    installed, a JSON field stores the list of floats instead.
    """
    id = models.BigAutoField(primary_key=True)
    span = models.ForeignKey(Span, related_name='embeddings', on_delete=models.CASCADE)
    model_name = models.CharField(max_length=128)
    dim = models.IntegerField()
    version = models.CharField(max_length=32, default='v0')
    if VectorField:
        vector = VectorField(dimensions=None)  # type: ignore
    else:
        vector = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Embedding {self.model_name} for span {self.span_id}"


class CourtEvent(models.Model):
    """Represents a derived event mapped from spans and rule logic."""

    id = models.BigAutoField(primary_key=True)
    process = models.ForeignKey(Process, related_name='events', on_delete=models.CASCADE)
    event_type = models.ForeignKey(EventType, on_delete=models.PROTECT)
    date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default='')
    spans = models.ManyToManyField(Span, through='CourtEventEvidence')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self) -> str:
        return f"{self.event_type.code} for process {self.process_id}"


class CourtEventEvidence(models.Model):
    """Associates events with their evidence (spans/documents)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    span = models.ForeignKey(Span, on_delete=models.CASCADE)
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    evidence_confidence = models.FloatField(default=0.0)
    notes = models.TextField(blank=True, default='')


class Seizure(models.Model):
    """Structured data describing a penhora (seizure)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    span = models.ForeignKey(Span, on_delete=models.SET_NULL, null=True, blank=True)
    subtype = models.CharField(max_length=64, blank=True, default='')
    amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    percent = models.FloatField(null=True, blank=True)
    asset_identifier = models.CharField(max_length=128, blank=True, default='')
    status = models.CharField(max_length=32, blank=True, default='')
    date_ordered = models.DateField(null=True, blank=True)
    date_effective = models.DateField(null=True, blank=True)
    date_converted = models.DateField(null=True, blank=True)
    date_cancelled = models.DateField(null=True, blank=True)


class Expropriation(models.Model):
    """Structured data describing expropriation (leilão/adjudicação/AIP)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    span = models.ForeignKey(Span, on_delete=models.SET_NULL, null=True, blank=True)
    path = models.CharField(max_length=64, blank=True, default='')
    stage = models.CharField(max_length=64, blank=True, default='')
    auction_round = models.IntegerField(null=True, blank=True)
    base_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    hammer_price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)


class EnforcementAction(models.Model):
    """Generic constriction (bloqueio, constrição) before penhora."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    span = models.ForeignKey(Span, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=64)
    result = models.CharField(max_length=64, blank=True, default='')
    value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    date_ordered = models.DateField(null=True, blank=True)
    date_effective = models.DateField(null=True, blank=True)
    converted_to_penhora = models.BooleanField(default=False)


class AgreementPlan(models.Model):
    """Details of homologated agreements (parcelamentos)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    number_of_installments = models.IntegerField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    def __str__(self) -> str:
        return f"Agreement for event {self.event_id}"


class Suspension(models.Model):
    """Represents a suspension per art. 921 of CPC."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    start_date = models.DateField(null=True, blank=True)
    milestone_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=64, blank=True, default='')


class IdpjEntry(models.Model):
    """Represents a piercing the corporate veil (IDPJ) entry."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    person_name = models.CharField(max_length=255)
    masked_identifier = models.CharField(max_length=32)
    reason = models.TextField(blank=True, default='')
    result = models.CharField(max_length=64, blank=True, default='')


class ProcessDeadline(models.Model):
    """Represents procedural deadlines (prazo processual)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    deadline_type = models.CharField(max_length=64)
    days = models.IntegerField()
    working_days = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)


class Calculation(models.Model):
    """Represents calculation updates (cálculos atualizados)."""
    id = models.BigAutoField(primary_key=True)
    event = models.ForeignKey(CourtEvent, on_delete=models.CASCADE)
    index_name = models.CharField(max_length=64, blank=True, default='')
    interest_rate = models.FloatField(null=True, blank=True)
    updated_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    competence = models.CharField(max_length=64, blank=True, default='')


class PricingRun(models.Model):
    """Logs a pricing calculation run for a process."""
    id = models.BigAutoField(primary_key=True)
    process = models.ForeignKey(Process, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)
    total_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))


class ProcessPricing(models.Model):
    """Stores the final pricing outcome per process."""
    id = models.BigAutoField(primary_key=True)
    process = models.ForeignKey(Process, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))