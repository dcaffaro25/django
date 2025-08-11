# NORD/multitenancy/urls.py

from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import CustomUserViewSet, CompanyViewSet, EntityViewSet, EntityTreeView, LoginView, LogoutView, IntegrationRuleViewSet
from accounting.views import CurrencyViewSet
from .api_utils import BulkImportPreview, BulkImportExecute
from .views import ValidateRuleView, ExecuteRuleView#, TriggerListView
from .api_utils import BulkImportTemplateDownloadView


router = DefaultRouter()
router.trailing_slash = r'/?'

router.register(r'users', CustomUserViewSet, basename='user')
router.register(r'companies', CompanyViewSet, basename='company')
#router.register(r'entities', EntityViewSet, basename='entity')
router.register(r'currencies', CurrencyViewSet)
router.register(r'integration-rules', IntegrationRuleViewSet)

urlpatterns = [
    re_path(r'^login/?$', LoginView.as_view(), name='login'),
    re_path(r'^logout/?$', LogoutView.as_view(), name='logout'),

    # Make the prefix itself optional-slash:
    re_path(r'^api/core/?', include(router.urls)),

    re_path(r'^api/core/validate-rule/?$', ValidateRuleView.as_view(), name='validate-rule'),
    re_path(r'^api/core/test-rule/?$', ExecuteRuleView.as_view(), name='execute-rule'),
    re_path(r'^api/core/bulk-import-preview/?$', BulkImportPreview.as_view(), name='bulk-import-preview'),
    re_path(r'^api/core/bulk-import-execute/?$', BulkImportExecute.as_view(), name='bulk-import-execute'),
    re_path(r'^api/core/bulk-import-template/?$', BulkImportTemplateDownloadView.as_view(), name='bulk-import-template'),
]
