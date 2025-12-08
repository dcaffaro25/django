"""
HTML View for ETL Preview - Provides a user-friendly web interface
"""
from django.shortcuts import render
from django.views import View
from django.http import JsonResponse
from django.conf import settings
from rest_framework import status
from .models import Company
from .etl_service import ETLPipelineService

# Import _scrub_json from views module (it's defined there)
# We'll define it here to avoid circular imports
import math

def _scrub_json(o):
    """Replace NaN/±Inf with None (valid JSON), recurse containers."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: _scrub_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_scrub_json(v) for v in o]
    # Convert numpy scalars if present
    if hasattr(o, "item") and callable(getattr(o, "item", None)):
        try:
            return _scrub_json(o.item())
        except Exception:
            pass
    return o

class ETLPreviewHTMLView(View):
    """
    HTML view for ETL Preview with file upload form.
    
    GET: Shows upload form
    POST: Processes file and shows results
    """
    
    template_name = 'multitenancy/etl_preview.html'
    
    def get(self, request):
        """Show the file upload form."""
        companies = Company.objects.filter(is_deleted=False).order_by('name')
        context = {
            'companies': companies,
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Process the uploaded file and return JSON response."""
        if 'file' not in request.FILES:
            return JsonResponse({
                'error': 'No file provided. Upload an Excel file.'
            }, status=400)
        
        company_id = request.POST.get('company_id')
        if not company_id:
            return JsonResponse({
                'error': 'No company_id provided.'
            }, status=400)
        
        try:
            company_id = int(company_id)
        except (ValueError, TypeError):
            return JsonResponse({
                'error': f'Invalid company_id: {company_id}'
            }, status=400)
        
        file = request.FILES['file']
        
        # Extract auto_create_journal_entries from request (can be JSON string or dict)
        auto_create_journal_entries = None
        if 'auto_create_journal_entries' in request.POST:
            import json
            auto_create_val = request.POST.get('auto_create_journal_entries')
            if isinstance(auto_create_val, str):
                try:
                    auto_create_journal_entries = json.loads(auto_create_val)
                except json.JSONDecodeError:
                    auto_create_journal_entries = {}
            elif isinstance(auto_create_val, dict):
                auto_create_journal_entries = auto_create_val
        
        # Extract row_limit from request (default: 10, 0 = process all rows)
        row_limit = 10  # Default for testing
        if 'row_limit' in request.POST:
            try:
                row_limit = int(request.POST.get('row_limit'))
            except (ValueError, TypeError):
                row_limit = 10  # Fallback to default
        
        try:
            service = ETLPipelineService(
                company_id=company_id,
                file=file,
                commit=False,  # Preview mode
                auto_create_journal_entries=auto_create_journal_entries,
                row_limit=row_limit
            )
            
            result = service.execute()
            result = _scrub_json(result)
            
            return JsonResponse(result, status=200 if result.get('success') else 400)
            
        except Exception as e:
            import traceback
            return JsonResponse({
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=500)

