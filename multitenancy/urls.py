# NORD/multitenancy/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomUserViewSet, CompanyViewSet, EntityViewSet, EntityTreeView, LoginView, LogoutView, IntegrationRuleViewSet
from accounting.views import CurrencyViewSet
from .api_utils import BulkImportPreview, BulkImportExecute
from .views import ValidateRuleView, ExecuteRuleView#, TriggerListView
from .api_utils import BulkImportTemplateDownloadView


router = DefaultRouter()
router.register(r'users', CustomUserViewSet, basename='user')
router.register(r'companies', CompanyViewSet, basename='company')
#router.register(r'entities', EntityViewSet, basename='entity')
router.register(r'currencies', CurrencyViewSet)
router.register(r'integration-rules', IntegrationRuleViewSet)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),  # Add login URL
    path('logout/', LogoutView.as_view(), name='logout'),
    path('api/core/', include(router.urls)),
    path("api/core/validate-rule/", ValidateRuleView.as_view(), name="validate-rule"),
    path("api/core/test-rule/", ExecuteRuleView.as_view(), name="execute-rule"),
    #path("api/core/integration-rules/triggers/", TriggerListView.as_view(), name="list-triggers"),
    path('api/core/bulk-import-preview/', BulkImportPreview.as_view(), name='bulk-import-preview'),
    path('api/core/bulk-import-execute/', BulkImportExecute.as_view(), name='bulk-import-execute'),
    path('api/core/bulk-import-template/', BulkImportTemplateDownloadView.as_view(), name='bulk-import-template'),
    
]
