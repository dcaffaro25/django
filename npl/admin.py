"""
Admin registrations for the NPL app.

Register models so they appear in the Django admin with some basic list
display and filtering options.  The tenant_id field is exposed to aid
multi‑tenant management.
"""
from django.contrib import admin


from . import models



@admin.register(models.Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ('id', 'case_number', 'tenant_id', 'created_at')
    search_fields = ('case_number',)
    list_filter = ('tenant_id',)


@admin.register(models.Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('id', 'process', 'doc_type', 'embedding_mode', 'num_pages', 'created_at')
    search_fields = ('id', 'process__case_number')
    list_filter = ('doc_type', 'process__tenant_id', 'embedding_mode')
    fieldsets = (
        (None, {
            'fields': ('file', 'process', 'embedding_mode')
        }),
        ('OCR & Metadados', {
            'fields': ('ocr_text', 'doc_type', 'doctype_confidence', 'processing_stats')
        }),
    )


@admin.register(models.Span)
class SpanAdmin(admin.ModelAdmin):
    list_display = ('id', 'document', 'label', 'page', 'confidence', 'strong_anchor_count', 'weak_anchor_count', 'negative_anchor_count', 'anchors_pos')
    search_fields = ('label', 'text')
    list_filter = ('label', 'document__process__tenant_id')



@admin.register(models.EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ('code', 'description')
    search_fields = ('code', 'description')


@admin.register(models.CourtEvent)
class CourtEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'process', 'event_type', 'date')
    search_fields = ('process__case_number', 'event_type__code')


@admin.register(models.CourtEventEvidence)
class CourtEventEvidenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'document', 'span', 'evidence_confidence')
    list_filter = ('event__event_type',)


@admin.register(models.Seizure)
class SeizureAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'subtype', 'amount', 'status')
    list_filter = ('subtype', 'status')


@admin.register(models.Expropriation)
class ExpropriationAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'path', 'stage', 'auction_round')


@admin.register(models.EnforcementAction)
class EnforcementActionAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'action_type', 'result', 'value')
    list_filter = ('action_type',)


@admin.register(models.AgreementPlan)
class AgreementPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'number_of_installments', 'total_amount')


@admin.register(models.Suspension)
class SuspensionAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'start_date', 'milestone_date', 'status')


@admin.register(models.IdpjEntry)
class IdpjEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'person_name', 'masked_identifier', 'result')


@admin.register(models.ProcessDeadline)
class ProcessDeadlineAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'deadline_type', 'days', 'working_days')


@admin.register(models.Calculation)
class CalculationAdmin(admin.ModelAdmin):
    list_display = ('id', 'event', 'index_name', 'interest_rate', 'updated_value')


@admin.register(models.PricingRun)
class PricingRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'process', 'total_price', 'created_at')


@admin.register(models.ProcessPricing)
class ProcessPricingAdmin(admin.ModelAdmin):
    list_display = ('id', 'process', 'price', 'created_at')
    
@admin.register(models.SpanRule)
class SpanRuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'description', 'embedding_model')
    search_fields = ('label', 'anchors_strong', 'anchors_weak', 'anchors_negative')
    list_filter = ('embedding_model',)
    readonly_fields = ('anchor_embeddings',)
    fieldsets = (
        (None, {
            'fields': ('label', 'description')
        }),
        ('Âncoras', {
            'fields': ('anchors_strong', 'anchors_weak', 'anchors_negative'),
            'description': "Separe múltiplas âncoras por ';'."
        }),
        ('Embeddings', {
            'fields': ('embedding_model', 'anchor_embeddings'),
            'description': "As embeddings são geradas automaticamente ao salvar."
        }),
    )

@admin.register(models.DocTypeRule)
class DocTypeRuleAdmin(admin.ModelAdmin):
    list_display = ('doc_type', 'description')
    search_fields = ('doc_type', 'description')
    fieldsets = (
        (None, {
            'fields': ('doc_type', 'description')
        }),
        ('Âncoras', {
            'fields': ('anchors_strong', 'anchors_weak', 'anchors_negative'),
            'description': "Separe múltiplas âncoras por ';'."
        }),
    )