"""
URL patterns for feedback endpoints.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('doctype/<int:document_id>', views.doctype_feedback, name='feedback-doctype'),
    path('span/<int:document_id>', views.span_feedback, name='feedback-span'),
    path('ecode/<int:span_id>', views.ecode_feedback, name='feedback-ecode'),
    path('search', views.search_feedback, name='feedback-search'),
    path('train/<str:task>', views.train_task, name='train-task'),
    path('models/versions', views.ModelVersionListView.as_view(), name='model-versions'),
]