from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MLModelViewSet#, TaskStatusView

router = DefaultRouter()
router.register(r"ml-models", MLModelViewSet, basename="ml-model")
#router.register(r"ml-task-status", TaskStatusView, basename="ml-task-status")

urlpatterns = [
    path("", include(router.urls)),
]
