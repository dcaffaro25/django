"""
Django admin configuration for knowledge base models.
"""
from django.contrib import admin
from .models import KnowledgeBase, KnowledgeDocument, Answer, AnswerFeedback


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'gemini_store_name', 'created_at']
    list_filter = ['company', 'created_at']
    search_fields = ['name', 'gemini_store_name']
    readonly_fields = ['gemini_store_name', 'created_at', 'updated_at']


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'knowledge_base', 'status', 'created_at']
    list_filter = ['status', 'knowledge_base', 'created_at']
    search_fields = ['filename', 'gemini_doc_name']
    readonly_fields = ['status', 'error', 'gemini_doc_name', 'created_at', 'updated_at']


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['question', 'knowledge_base', 'created_at']
    list_filter = ['knowledge_base', 'created_at']
    search_fields = ['question', 'answer_text']
    readonly_fields = ['created_at']


@admin.register(AnswerFeedback)
class AnswerFeedbackAdmin(admin.ModelAdmin):
    list_display = ['answer', 'rating', 'missing_info', 'created_at']
    list_filter = ['rating', 'missing_info', 'created_at']
    search_fields = ['comment']
    readonly_fields = ['created_at']
