"""nord_backend URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from accounting.views_celery import start_task, task_status

urlpatterns = [
    re_path(r'^admin/?', admin.site.urls),
    re_path(r'^home/?$', views.index, name='index'),
    path('api/meta/', include('api_meta.urls')),
    # Platform-admin API (NOT the Django /admin/ panel — these are React-
    # facing DRF endpoints at /api/admin/*, gated by IsSuperUser). No
    # tenant prefix on purpose: dcaffaro needs to see every user /
    # company in the fleet.
    path('api/admin/', include('multitenancy.urls_admin')),
    #re_path(r'^(?P<tenant_id>[^/]+)/', include('multitenancy.urls')),
    path('', include('multitenancy.urls')),
    path('', include('core.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('accounting.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('hr.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('multitenancy.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('billing.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('inventory.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('ML.urls')),
    re_path(r'^(?P<tenant_id>[^/]+)/', include('knowledge_base.urls')),
    # ERP API routes are merged under accounting/urls.py (api/) so they resolve; a standalone include here never runs.
    #path('api/', include('accounting.urls')),
    # POST /api/token/ → DRF obtain_auth_token: returns {token} for the
    # username/password SPA login flow. The client sends it back as
    # Authorization: Token <key>, which DRF TokenAuthentication parses.
    re_path(r'^api/token/?$', obtain_auth_token, name='obtain_auth_token'),
    # SimpleJWT endpoints retained but not used by the SPA (other clients may).
    re_path(r'^api/jwt/?$', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    re_path(r'^api/jwt/refresh/?$', TokenRefreshView.as_view(), name='token_refresh'),
    path("celery/start/", start_task, name="celery_start"),
    path("celery/status/<str:task_id>/", task_status, name="celery_status"),
    re_path('', include('npl.urls')),
    re_path('', include('feedback.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)