from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MLModelViewSet

router = DefaultRouter()
router.register(r"ml-models", MLModelViewSet, basename="ml-model")

urlpatterns = [
    path("", include(router.urls)),
]
