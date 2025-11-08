"""
Command to run the full pipeline on all documents.

This management command iterates over all documents in the database and
schedules OCR, labelling, embedding and indexing tasks.  It is useful
for bootstraping the demo environment.
"""
from django.core.management.base import BaseCommand
from npl_project.apps.npl import models, tasks


class Command(BaseCommand):
    help = "Run OCR and labelling pipeline for all documents"

    def handle(self, *args, **options):
        docs = models.Document.objects.all()
        for doc in docs:
            tasks.ocr_pipeline_task.delay(doc.id)
            self.stdout.write(f"Scheduled pipeline for document {doc.id}")