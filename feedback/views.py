"""
API views for feedback endpoints.

These endpoints collect user judgments on document type classification, span
extraction, event code mapping and search ranking.  The data can later be
used to improve the underlying models.
"""
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404

from npl import models as npl_models
from . import models
from . import serializers


@api_view(['POST'])
def doctype_feedback(request, document_id: int):
    """Record feedback on the document type suggestion."""
    document = get_object_or_404(npl_models.Document, pk=document_id)
    accepted = request.data.get('accepted', True)
    edited_value = request.data.get('edited_value')
    session = models.JudgmentSession.objects.create(user_identifier='anonymous')
    cset = models.CandidateSet.objects.create(session=session, task_type='doctype', reference_id=document_id)
    candidate = models.Candidate.objects.create(candidate_set=cset, object_type='document', object_id=document_id)
    models.UserJudgment.objects.create(candidate=candidate, accepted=accepted, edited_value=edited_value)
    # Optionally update document type
    if edited_value:
        document.doc_type = edited_value
        document.save(update_fields=['doc_type'])
    return Response({'status': 'recorded'})


@api_view(['POST'])
def span_feedback(request, document_id: int):
    """Record feedback on spans for a document."""
    accepted_spans = request.data.get('accepted_span_ids', [])
    edited_spans = request.data.get('edited_spans', [])  # list of {text,label}
    session = models.JudgmentSession.objects.create(user_identifier='anonymous')
    cset = models.CandidateSet.objects.create(session=session, task_type='span', reference_id=document_id)
    # Mark accepted spans
    for span_id in accepted_spans:
        candidate = models.Candidate.objects.create(candidate_set=cset, object_type='span', object_id=span_id)
        models.UserJudgment.objects.create(candidate=candidate, accepted=True)
    # Edited spans: create or update spans
    for edited in edited_spans:
        text = edited.get('text', '')
        label = edited.get('label', 'UNKNOWN')
        span = npl_models.Span.objects.create(
            document_id=document_id,
            label=label,
            text=text,
            page=0,
            char_start=0,
            char_end=len(text),
            confidence=1.0,
        )
        candidate = models.Candidate.objects.create(candidate_set=cset, object_type='span', object_id=span.id)
        models.UserJudgment.objects.create(candidate=candidate, accepted=True, edited_value={'label': label, 'text': text})
    return Response({'status': 'recorded'})


@api_view(['POST'])
def ecode_feedback(request, span_id: int):
    """Record feedback on event code suggestions for a span."""
    accepted_codes = request.data.get('accepted_codes', [])
    edited_codes = request.data.get('edited_codes', [])
    session = models.JudgmentSession.objects.create(user_identifier='anonymous')
    cset = models.CandidateSet.objects.create(session=session, task_type='ecode', reference_id=span_id)
    candidate = models.Candidate.objects.create(candidate_set=cset, object_type='span', object_id=span_id)
    models.UserJudgment.objects.create(candidate=candidate, accepted=True, edited_value={'accepted_codes': accepted_codes, 'edited_codes': edited_codes})
    return Response({'status': 'recorded'})


@api_view(['POST'])
def search_feedback(request):
    """Record feedback on search results ranking."""
    results = request.data.get('results', [])  # list of {'span_id': int, 'order': int}
    session = models.JudgmentSession.objects.create(user_identifier='anonymous')
    cset = models.CandidateSet.objects.create(session=session, task_type='search')
    for item in results:
        span_id = item.get('span_id')
        order = item.get('order')
        candidate = models.Candidate.objects.create(candidate_set=cset, object_type='span', object_id=span_id)
        models.UserJudgment.objects.create(candidate=candidate, accepted=True, order=order)
    return Response({'status': 'recorded'})


@api_view(['POST'])
def train_task(request, task: str):
    """Trigger training of a task (doctype/span/ecode/search)."""
    # In a real system this would schedule an asynchronous job to train the
    # corresponding model using data from UserJudgment.  Here we just log a
    # placeholder and record a new model version.
    session = models.JudgmentSession.objects.create(user_identifier='system-trainer')
    models.ModelVersion.objects.create(task=task, version_name='v0', metrics={})
    return Response({'status': f'training scheduled for {task}'})


class ModelVersionListView(generics.ListAPIView):
    """List available model versions."""
    serializer_class = serializers.ModelVersionSerializer
    queryset = models.ModelVersion.objects.all().order_by('task', '-created_at')