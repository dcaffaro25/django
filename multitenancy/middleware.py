from django.http import JsonResponse
from django.urls import resolve
from .models import Company
from django.http import Http404
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .utils import resolve_tenant

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log the incoming request and headers
        print(f"Path: {request.path}")
        print(f"Headers: {request.headers}")
        
        if request.path.startswith('/login'):
            return self.get_response(request)
        
        # Bypass tenant check for admin, login/logout, or core API paths
        if (
            request.path.startswith('/admin') or
            request.path.startswith('/home') or
            request.path.startswith('/api/login') or
            request.path.startswith('/api/logout') or
            request.path.startswith('/api/core') or
            request.path.startswith('/docs') or
            '/knowledge-base' in request.path
        ):
            return self.get_response(request)

        # Extract the tenant identifier
        path_parts = request.path_info.strip('/').split('/')
        subdomain = path_parts[0] if path_parts else None
        #print(subdomain)
        
        # Check if the user is authenticated
        if not request.user.is_authenticated and subdomain != 'testco':
            try:
                auth = TokenAuthentication()
                auth_result = auth.authenticate(request)
                if auth_result is not None:
                    user, token = auth_result
                    request.user = user
                    request.auth = token
            except AuthenticationFailed:
                # Don't return 401 here - let the view handle permissions
                # Some views (like knowledge-base) allow unauthenticated access
                # Just log and continue - the view's permission_classes will decide
                print(f"[TenantMiddleware] Authentication failed for {request.path}, but allowing request to continue")
                pass

        # Handle 'all' tenants for superusers
        if subdomain == 'all':
            if request.user.is_superuser:
                request.tenant = 'all'
            else:
                raise Http404("Not authorized to view all tenants")
        else:
            # Fetch tenant by subdomain
            try:
                request.tenant = resolve_tenant(subdomain)
            except Company.DoesNotExist:
                raise Http404("Company not found")
        #print(request.tenant)
        return self.get_response(request)
