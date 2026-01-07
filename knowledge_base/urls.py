"""
URL patterns for knowledge base API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'knowledge-bases', views.KnowledgeBaseViewSet, basename='knowledgebase')
router.register(r'documents', views.KnowledgeDocumentViewSet, basename='knowledgedocument')
router.register(r'answers/(?P<answer_id>\d+)/feedback', views.AnswerFeedbackView, basename='answerfeedback')

urlpatterns = [
    path('api/', include(router.urls)),
    path('knowledge-base/', views.KnowledgeBaseIndexView.as_view(), name='knowledge-base-index'),
]
