# NORD/multitenancy/urls.py

from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import (
    CustomUserViewSet, CompanyViewSet, EntityViewSet, EntityTreeView,
    LoginView, LogoutView, IntegrationRuleViewSet, ChangePasswordView,
    UserCreateView, PasswordResetForceView, AdminForcePasswordView,
    SubstitutionRuleViewSet, ValidateRuleView, ExecuteRuleView, BulkImportAPIView,
    # ETL Pipeline views
    ImportTransformationRuleViewSet, ETLPipelineLogViewSet,
    ETLPipelinePreviewView, ETLPipelineExecuteView, ETLPipelineAnalyzeView,
    ETLPipelineErrorReportView,
)
from .views_etl_html import ETLPreviewHTMLView, ETLExecuteHTMLView
from accounting.views import CurrencyViewSet
from .api_utils import BulkImportPreview, BulkImportExecute, BulkImportTemplateDownloadView


router = DefaultRouter()
router.trailing_slash = r'/?'

router.register(r'users', CustomUserViewSet, basename='user')
router.register(r'companies', CompanyViewSet, basename='company')
#router.register(r'entities', EntityViewSet, basename='entity')
router.register(r'currencies', CurrencyViewSet)
router.register(r'integration-rules', IntegrationRuleViewSet)
router.register(r'substitution-rules', SubstitutionRuleViewSet, basename='substitutionrule')

# ETL Pipeline routers
router.register(r'etl/transformation-rules', ImportTransformationRuleViewSet, basename='etl-transformation-rule')
router.register(r'etl/logs', ETLPipelineLogViewSet, basename='etl-log')

urlpatterns = [
    re_path(r'^login/?$', LoginView.as_view(), name='login'),
    re_path(r'^logout/?$', LogoutView.as_view(), name='logout'),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("reset-password/", PasswordResetForceView.as_view(), name="reset-password"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path("force-reset-password/", AdminForcePasswordView.as_view(), name="force-reset-password"),
    
    path('api/core/', include(router.urls)),
    path('api/core/bulk-import/', BulkImportAPIView.as_view(), name='bulk-import'),
    # Make the prefix itself optional-slash:
    re_path(r'^api/core/?', include(router.urls)),

    re_path(r'^api/core/validate-rule/?$', ValidateRuleView.as_view(), name='validate-rule'),
    re_path(r'^api/core/test-rule/?$', ExecuteRuleView.as_view(), name='execute-rule'),
    re_path(r'^api/core/bulk-import-preview/?$', BulkImportPreview.as_view(), name='bulk-import-preview'),
    re_path(r'^api/core/bulk-import-execute/?$', BulkImportExecute.as_view(), name='bulk-import-execute'),
    re_path(r'^api/core/bulk-import-template/?$', BulkImportTemplateDownloadView.as_view(), name='bulk-import-template'),
    
    # ETL Pipeline endpoints
    re_path(r'^api/core/etl/preview/?$', ETLPipelinePreviewView.as_view(), name='etl-preview'),
    re_path(r'^api/core/etl/execute/?$', ETLPipelineExecuteView.as_view(), name='etl-execute'),
    re_path(r'^api/core/etl/analyze/?$', ETLPipelineAnalyzeView.as_view(), name='etl-analyze'),
    re_path(r'^api/core/etl/logs/(?P<pk>\d+)/error-report/?$', ETLPipelineErrorReportView.as_view(), name='etl-error-report'),
    
    # ETL Pipeline HTML interface
    re_path(r'^etl/preview/?$', ETLPreviewHTMLView.as_view(), name='etl-preview-html'),
    re_path(r'^etl/execute/?$', ETLExecuteHTMLView.as_view(), name='etl-execute-html'),
]
