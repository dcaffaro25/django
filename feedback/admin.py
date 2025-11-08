"""
Admin registrations for feedback models.
"""
from django.contrib import admin
from . import models


@admin.register(models.JudgmentSession)
class JudgmentSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_identifier', 'started_at', 'finished_at')


@admin.register(models.CandidateSet)
class CandidateSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'task_type', 'reference_id', 'created_at')


@admin.register(models.Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate_set', 'object_type', 'object_id', 'rank')


@admin.register(models.UserJudgment)
class UserJudgmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'accepted', 'order', 'created_at')


@admin.register(models.RetrieverRun)
class RetrieverRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'run_type', 'created_at')


@admin.register(models.ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'task', 'version_name', 'created_at')