"""
View for previewing financial statement templates.
Provides a simple interface to select a template and generate a preview.
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import date, datetime
from decimal import Decimal

from multitenancy.utils import resolve_tenant
from accounting.models import Account, Currency
from accounting.models_financial_statements import FinancialStatementTemplate
from accounting.services.financial_statement_service import FinancialStatementGenerator


@login_required
@require_http_methods(["GET"])
def template_preview_page(request, tenant_id=None):
    """
    Main page to select a template and generate preview.
    """
    # Resolve tenant/company
    if not tenant_id:
        return JsonResponse({'error': 'Tenant ID is required'}, status=400)
    
    company = resolve_tenant(tenant_id)
    if not company:
        return JsonResponse({'error': 'Company not found'}, status=400)
    
    company_id = company.id if hasattr(company, 'id') else company
    
    # Get all templates for this company
    templates = FinancialStatementTemplate.objects.filter(
        company_id=company_id,
        is_active=True
    ).order_by('report_type', 'name')
    
    context = {
        'templates': templates,
        'company_id': company_id,
        'tenant_id': tenant_id,
    }
    
    return render(request, 'accounting/template_preview.html', context)


@login_required
@require_http_methods(["POST"])
def generate_preview(request, tenant_id=None):
    """
    Generate a preview of a financial statement.
    """
    # Resolve tenant/company
    if not tenant_id:
        return JsonResponse({'error': 'Tenant ID is required'}, status=400)
    
    company = resolve_tenant(tenant_id)
    if not company:
        return JsonResponse({'error': 'Company not found'}, status=400)
    
    company_id = company.id if hasattr(company, 'id') else company
    
    # Get parameters
    template_id = request.POST.get('template_id')
    start_date_str = request.POST.get('start_date')
    end_date_str = request.POST.get('end_date')
    as_of_date_str = request.POST.get('as_of_date')
    include_pending = request.POST.get('include_pending', 'false').lower() == 'true'
    debug_accounts = request.POST.get('debug_accounts', 'false').lower() == 'true'
    
    if not template_id:
        return JsonResponse({'error': 'template_id is required'}, status=400)
    
    try:
        template = FinancialStatementTemplate.objects.get(
            id=template_id,
            company_id=company_id
        )
    except FinancialStatementTemplate.DoesNotExist:
        return JsonResponse({'error': 'Template not found'}, status=404)
    
    # Parse dates
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today().replace(month=1, day=1)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else date.today()
        as_of_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date() if as_of_date_str else end_date
    except ValueError as e:
        return JsonResponse({'error': f'Invalid date format: {e}'}, status=400)
    
    # Generate preview
    try:
        generator = FinancialStatementGenerator(company_id=company_id)
        preview_data = generator.preview_statement(
            template=template,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            include_pending=include_pending,
        )
        
        # Add debug information if requested
        if debug_accounts:
            preview_data['debug_info'] = _get_debug_info(
                generator, template, start_date, end_date, as_of_date, include_pending
            )
        
        return JsonResponse(preview_data)
    
    except Exception as e:
        import traceback
        return JsonResponse({
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


def _get_debug_info(generator, template, start_date, end_date, as_of_date, include_pending):
    """Get detailed debug information for accounts."""
    debug_info = {}
    
    for line_template in template.line_templates.all().order_by('line_number'):
        if line_template.line_type in ('header', 'spacer') or not line_template.account:
            continue
        
        account = line_template.account
        account_info = {
            'account_id': account.id,
            'account_code': account.account_code,
            'account_name': account.name,
            'is_leaf': account.is_leaf(),
            'account_direction': account.account_direction,
            'stored_balance': float(account.balance),
            'balance_date': str(account.balance_date) if account.balance_date else None,
        }
        
        if account.is_leaf():
            # Leaf account details
            from django.db.models import Sum
            from accounting.models import JournalEntry
            
            state_filter = Q(state='posted')
            if include_pending:
                state_filter = Q(state__in=['posted', 'pending'])
            
            entries = JournalEntry.objects.filter(
                account=account,
                transaction__company_id=generator.company_id,
            ).filter(state_filter)
            
            if start_date:
                entries = entries.filter(
                    Q(date__gte=start_date) | (Q(date__isnull=True) & Q(transaction__date__gte=start_date))
                )
            if end_date:
                entries = entries.filter(
                    Q(date__lte=end_date) | (Q(date__isnull=True) & Q(transaction__date__lte=end_date))
                )
            
            totals = entries.aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )
            
            account_info['entry_count'] = entries.count()
            account_info['total_debit'] = float(totals['total_debit'] or Decimal('0.00'))
            account_info['total_credit'] = float(totals['total_credit'] or Decimal('0.00'))
            account_info['net_movement'] = float(account_info['total_debit'] - account_info['total_credit'])
            account_info['calculated_balance'] = float(account_info['net_movement'] * account.account_direction)
        else:
            # Parent account details
            children = account.get_children().filter(company_id=generator.company_id)
            account_info['children_count'] = children.count()
            account_info['children'] = []
            
            total_children_balance = Decimal('0.00')
            for child in children:
                child_balance = generator._calculate_account_balance_with_children(
                    account=child,
                    include_pending=include_pending,
                    beginning_date=start_date if template.report_type == 'income_statement' else None,
                    end_date=end_date,
                )
                total_children_balance += child_balance
                account_info['children'].append({
                    'id': child.id,
                    'code': child.account_code,
                    'name': child.name,
                    'balance': float(child_balance),
                })
            
            account_info['sum_of_children'] = float(total_children_balance)
            parent_balance = generator._calculate_account_balance_with_children(
                account=account,
                include_pending=include_pending,
                beginning_date=start_date if template.report_type == 'income_statement' else None,
                end_date=end_date,
            )
            account_info['parent_calculated_balance'] = float(parent_balance)
            account_info['balance_match'] = abs(total_children_balance - parent_balance) < Decimal('0.01')
        
        debug_info[line_template.line_number] = account_info
    
    return debug_info

