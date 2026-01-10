# NORD/multitenancy/views.py
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login, logout
from rest_framework import views, viewsets, generics, status, serializers
from rest_framework.response import Response
from .models import CustomUser, Company, Entity, IntegrationRule, SubstitutionRule, ImportTransformationRule, ETLPipelineLog
from .mixins import ScopedQuerysetMixin
from .serializers import (
    CustomUserSerializer, CompanySerializer, EntitySerializer, UserLoginSerializer,
    IntegrationRuleSerializer, EntityMiniSerializer, ChangePasswordSerializer,
    UserCreateSerializer, PasswordResetForceSerializer, SubstitutionRuleSerializer,
    ImportTransformationRuleSerializer, ImportTransformationRuleListSerializer,
    ETLPipelineLogSerializer, ETLPipelineLogListSerializer,
)
from .api_utils import create_csv_response, create_excel_response, _to_bool
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from accounting.serializers import AccountSerializer, CostCenterSerializer
from .formula_engine import validate_rule, run_rule_in_sandbox
from rest_framework.authtoken.models import Token
from django.core.mail import send_mail
from django.conf import settings
from .tasks import send_user_invite_email, send_user_email, run_import_job, execute_import_job
from django.utils import timezone
from datetime import timedelta
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from multitenancy.tasks import trigger_integration_event
from core.utils.json_sanitize import json_nullsafe
from celery import shared_task, group, chord
import numpy as np
import pandas as pd
import math
import hashlib

class LoginView(views.APIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()#(SessionAuthentication,)
    

    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.check_user(serializer.validated_data)
        
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)
        
        return Response({
            "detail": "Login successful",
            "token": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_superuser": user.is_superuser,
                "is_staff": user.is_staff,
                "must_change_password": getattr(user, "must_change_password", False),
            }
        }, status=status.HTTP_200_OK)

        
        '''
        username = request.data.get('username')
        password = request.data.get('password')
        print(username, password)
        user = authenticate(request, username=username, password=password)
        print(user)
        if user is not None:
            login(request, user)
            return Response({'detail': 'Login successful'})
        return Response({'detail': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)
        '''

class LogoutView(views.APIView):
    def post(self, request):
        logout(request)
        return Response({'detail': 'Logged out successfully'}, status=status.HTTP_200_OK)

#User = get_user_model()

class UserCreateView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = UserCreateSerializer
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        user = serializer.save()
        subject = "Your account has been created"
        message = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Your account has been created.\n"
            f"Username: {user.username}\n"
            f"Temporary Password: {user._temp_password}\n\n"
            f"Please log in and change your password immediately."
        )
        # enqueue email task
        #send_user_invite_email.delay(subject, message, user.email)

class ChangePasswordView(generics.UpdateAPIView):
    serializer_class = ChangePasswordSerializer
    model = CustomUser
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]

    def get_object(self, queryset=None):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not user.check_password(serializer.validated_data.get("old_password")):
            return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)
        
        user.must_change_password = False
        user.set_password(serializer.validated_data.get("new_password"))
        user.save()

        return Response({"detail": "Password updated successfully"}, status=status.HTTP_200_OK)


class PasswordResetForceView(generics.GenericAPIView):
    serializer_class = PasswordResetForceSerializer
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAdminUser]

    
    
    COOLDOWN_MINUTES = settings.PASSWORD_RESET_EMAIL_COOLDOWN  # ✅ minimum time before another email can be sent

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = CustomUser.objects.get(email=email)

        # ✅ Check cooldown
        if user.email_last_sent_at:
            next_allowed = user.email_last_sent_at + timedelta(minutes=self.COOLDOWN_MINUTES)
            if timezone.now() < next_allowed:
                remaining = (next_allowed - timezone.now()).seconds // 60 + 1
                return Response(
                    {"detail": f"Password reset email already sent. Try again in {remaining} minutes."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        # Generate temporary password
        temp_password = settings.TEMP_PASSWORD
        user.set_password(temp_password)
        user.must_change_password = True
        user.save()

        subject = "Your password has been reset"
        message = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Your password has been reset.\n"
            f"Temporary Password: {temp_password}\n\n"
            f"Please log in and change it immediately."
        )

        send_user_email.delay(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )

        # ✅ Track email sent
        user.mark_email_sent()

        return Response(
            {
                "detail": "Temporary password sent via email.",
                "email_last_sent_at": user.email_last_sent_at
            },
            status=status.HTTP_200_OK
        )

@method_decorator(csrf_exempt, name="dispatch")
class AdminForcePasswordView(generics.GenericAPIView):
    """
    Admin endpoint to reset a user's password.
    - If admin provides a 'new_password', use it.
    - Otherwise, use the standard fallback "ChangeMe123".
    - User is forced to change password on next login.
    """

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAdminUser]


    def post(self, request, *args, **kwargs):
        username_or_email = request.data.get("username") or request.data.get("email")
        new_password = request.data.get("new_password", None)

        if not username_or_email:
            return Response({"detail": "username or email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if "@" in username_or_email:
                user = CustomUser.objects.get(email=username_or_email)
            else:
                user = CustomUser.objects.get(username=username_or_email)
        except CustomUser.DoesNotExist:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # Use admin-provided password, otherwise fallback
        temp_password = new_password if new_password else settings.TEMP_PASSWORD#"ChangeMe123"
        user.set_password(temp_password)
        user.must_change_password = True
        user.save(update_fields=["password", "must_change_password"])

        return Response(
            {
                "detail": f"Password for {user.username} has been reset.",
                "temporary_password": temp_password,
                "must_change_password": user.must_change_password,
            },
            status=status.HTTP_200_OK
        )

class CustomUserViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = CustomUserSerializer
    
    def list(self, request, *args, **kwargs):
        format_type = request.query_params.get('response_format', 'json')
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        if format_type == 'csv':
            return create_csv_response(serializer.data)
        elif format_type == 'csv_semicolon':
            return create_csv_response(serializer.data, delimiter=';')
        elif format_type == 'excel':
            return create_excel_response(serializer.data)
        return super().list(request, *args, **kwargs)

class CompanyViewSet(viewsets.ModelViewSet):
    #queryset = Company.objects.none()
    serializer_class = CompanySerializer

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        #if hasattr(self.request, 'tenant'):
        #    if self.request.tenant == 'all':
        #        return Company.objects.all()
        #    else:
        #        return Company.objects.filter(pk=self.request.tenant.pk)
        #else:
        #    return Company.objects.none()  # Or handle as appropriate
        return Company.objects.all()

    @action(detail=False, methods=['get'], url_path='reconciliation-summary')
    def reconciliation_summary(self, request, tenant_id=None):
        """
        Returns transaction reconciliation summary statistics grouped by company (client/tenant).
        
        Query parameters (optional):
        - date_from: Filter transactions from this date
        - date_to: Filter transactions until this date
        - state__in: Comma-separated transaction states (pending,posted,canceled)
        - include_empty: If 'true', include companies with no transactions (default: false)
        
        Response:
        {
            "totals": { ... global summary ... },
            "by_company": [
                {
                    "company_id": 1,
                    "company_name": "Client ABC",
                    "subdomain": "clientabc",
                    "total_count": 50,
                    "balanced_count": 45,
                    ...
                },
                ...
            ]
        }
        """
        from django.db.models import Count, Sum, Q, Exists, OuterRef, Value, DecimalField
        from django.db.models.functions import Coalesce
        from accounting.models import Transaction, JournalEntry, Reconciliation
        
        # Get filter parameters
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        state_in = request.query_params.get('state__in')
        include_empty = request.query_params.get('include_empty', 'false').lower() in ('true', '1', 'yes')
        
        # Base transaction queryset
        tx_qs = Transaction.objects.all()
        
        if date_from:
            tx_qs = tx_qs.filter(date__gte=date_from)
        if date_to:
            tx_qs = tx_qs.filter(date__lte=date_to)
        if state_in:
            states = [s.strip() for s in state_in.split(',')]
            tx_qs = tx_qs.filter(state__in=states)
        
        # Subqueries for bank reconciliation status
        bank_linked_jes = JournalEntry.objects.filter(
            transaction_id=OuterRef('id'),
            account__bank_account__isnull=False
        )
        
        ok_recon = Reconciliation.objects.filter(
            journal_entries__id=OuterRef('id'),
            status__in=['matched', 'approved']
        )
        
        nonreconciled_bank_jes = bank_linked_jes.annotate(
            has_ok=Exists(ok_recon)
        ).filter(has_ok=False)
        
        reconciled_bank_jes = bank_linked_jes.annotate(
            has_ok=Exists(ok_recon)
        ).filter(has_ok=True)
        
        # Annotate transactions with bank recon flags
        tx_annotated = tx_qs.annotate(
            has_bank_jes=Exists(bank_linked_jes),
            has_nonreconciled_bank_jes=Exists(nonreconciled_bank_jes),
            has_reconciled_bank_jes=Exists(reconciled_bank_jes)
        )
        
        # Get all companies
        companies = self.get_queryset()
        results = []
        
        # Global totals
        global_totals = {
            'total_count': 0,
            'balanced_count': 0,
            'unbalanced_count': 0,
            'ready_to_post_count': 0,
            'pending_bank_recon_count': 0,
            'total_amount': 0,
            'by_state': {},
            'by_bank_recon_status': {'matched': 0, 'pending': 0, 'mixed': 0, 'na': 0}
        }
        
        for company in companies:
            company_tx = tx_annotated.filter(company_id=company.id)
            
            total_count = company_tx.count()
            
            # Handle companies with no transactions
            if total_count == 0:
                if include_empty:
                    # Add company with zero counts
                    results.append({
                        'company_id': company.id,
                        'company_name': company.name,
                        'subdomain': company.subdomain,
                        'total_count': 0,
                        'balanced_count': 0,
                        'unbalanced_count': 0,
                        'ready_to_post_count': 0,
                        'pending_bank_recon_count': 0,
                        'total_amount': 0.0,
                        'by_state': {},
                        'by_bank_recon_status': {'matched': 0, 'pending': 0, 'mixed': 0, 'na': 0}
                    })
                continue
            
            balanced_count = company_tx.filter(is_balanced=True).count()
            unbalanced_count = company_tx.filter(is_balanced=False).count()
            
            # Bank recon status counts
            na_count = company_tx.filter(has_bank_jes=False).count()
            matched_count = company_tx.filter(
                has_bank_jes=True, 
                has_nonreconciled_bank_jes=False
            ).count()
            pending_recon_count = company_tx.filter(
                has_bank_jes=True, 
                has_reconciled_bank_jes=False
            ).count()
            mixed_count = company_tx.filter(
                has_bank_jes=True, 
                has_reconciled_bank_jes=True, 
                has_nonreconciled_bank_jes=True
            ).count()
            
            # Ready to post: balanced + pending state + (no bank JEs OR all reconciled)
            ready_to_post_count = company_tx.filter(
                is_balanced=True,
                state='pending'
            ).filter(
                Q(has_bank_jes=False) | Q(has_nonreconciled_bank_jes=False)
            ).count()
            
            # Pending bank recon
            pending_bank_recon_count = company_tx.filter(
                has_bank_jes=True,
                has_nonreconciled_bank_jes=True
            ).count()
            
            # State breakdown
            state_counts = company_tx.values('state').annotate(count=Count('id'))
            by_state = {item['state']: item['count'] for item in state_counts}
            
            # Total amount
            total_amount = company_tx.aggregate(
                total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
            )['total']
            
            company_data = {
                'company_id': company.id,
                'company_name': company.name,
                'subdomain': company.subdomain,
                'total_count': total_count,
                'balanced_count': balanced_count,
                'unbalanced_count': unbalanced_count,
                'ready_to_post_count': ready_to_post_count,
                'pending_bank_recon_count': pending_bank_recon_count,
                'total_amount': float(total_amount or 0),
                'by_state': by_state,
                'by_bank_recon_status': {
                    'matched': matched_count,
                    'pending': pending_recon_count,
                    'mixed': mixed_count,
                    'na': na_count
                }
            }
            results.append(company_data)
            
            # Accumulate global totals
            global_totals['total_count'] += total_count
            global_totals['balanced_count'] += balanced_count
            global_totals['unbalanced_count'] += unbalanced_count
            global_totals['ready_to_post_count'] += ready_to_post_count
            global_totals['pending_bank_recon_count'] += pending_bank_recon_count
            global_totals['total_amount'] += float(total_amount or 0)
            global_totals['by_bank_recon_status']['matched'] += matched_count
            global_totals['by_bank_recon_status']['pending'] += pending_recon_count
            global_totals['by_bank_recon_status']['mixed'] += mixed_count
            global_totals['by_bank_recon_status']['na'] += na_count
            for state, count in by_state.items():
                global_totals['by_state'][state] = global_totals['by_state'].get(state, 0) + count
        
        # Sort by total_count descending
        results.sort(key=lambda x: x['total_count'], reverse=True)
        
        return Response({
            'totals': global_totals,
            'by_company': results
        }, status=status.HTTP_200_OK)


class EntityMiniViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Entity.objects.all()
    serializer_class = EntityMiniSerializer
    

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]

class EntityViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer
    

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    #def get_queryset(self):
    #    if hasattr(self.request, 'tenant'):
    #        if self.request.tenant == 'all':
    #            return Entity.objects.all()
    #        else:
    #            return Entity.objects.filter(company=self.request.tenant)
    #    else:
    #        return Entity.objects.none()  # Or handle as appropriate
    
    @action(detail=True, methods=['get'], url_path='context-options')
    def context_options(self, request, tenant_id=None, pk=None):
        try:
            entity = Entity.objects.get(id=pk)
    
            # Available = always from the inheritance logic
            available_accounts = entity.get_available_accounts()#leaf_only=True)
            available_cost_centers = entity.get_available_cost_centers()#leaf_only=True)
     
            # Selected = depends on whether the entity is inheriting
            if entity.inherit_accounts:
                selected_accounts = available_accounts
            else:
                selected_accounts = entity.accounts.all()
    
            if entity.inherit_cost_centers:
                selected_cost_centers = available_cost_centers
            else:
                selected_cost_centers = entity.cost_centers.all()
    
            return Response({
                "entity": entity.name,
                "inherit_accounts": entity.inherit_accounts,
                "inherit_cost_centers": entity.inherit_cost_centers,
                "available_accounts": AccountSerializer(available_accounts, many=True).data,
                "available_cost_centers": CostCenterSerializer(available_cost_centers, many=True).data,
                "selected_accounts": [a.id for a in selected_accounts],
                "selected_cost_centers": [c.id for c in selected_cost_centers],
            })
    
        except Entity.DoesNotExist:
            return Response({"error": "Entity not found"}, status=404)
    
    @action(detail=True, methods=['get'], url_path='effective-context')
    def effective_context_detail(self, request, tenant_id=None, pk=None):
        """
        Retrieve effective accounts and cost centers for a specific entity.
        """
        try:
            entity = Entity.objects.get(id=pk)
            accounts = entity.get_accounts()
            cost_centers = entity.get_cost_centers()

            account_data = AccountSerializer(accounts, many=True).data
            cost_center_data = CostCenterSerializer(cost_centers, many=True).data

            return Response({
                "entity": entity.name,
                "inherit_accounts": entity.inherit_accounts,
                "inherit_cost_centers": entity.inherit_cost_centers,
                "accounts": account_data,
                "cost_centers": cost_center_data
            }, status=status.HTTP_200_OK)
        
        except Entity.DoesNotExist:
            return Response({"error": "Entity not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], url_path='effective-context')
    def effective_context_list(self, request, tenant_id=None):
        """
        Retrieve effective accounts and cost centers for all entities.
        """
        entities = Entity.objects.all()
        results = []

        for entity in entities:
            accounts = entity.get_accounts()
            cost_centers = entity.get_cost_centers()
            
            account_data = AccountSerializer(accounts, many=True).data
            cost_center_data = CostCenterSerializer(cost_centers, many=True).data

            results.append({
                "entity": entity.name,
                "inherit_accounts": entity.inherit_accounts,
                "inherit_cost_centers": entity.inherit_cost_centers,
                "accounts": account_data,
                "cost_centers": cost_center_data
            })

        return Response(results, status=status.HTTP_200_OK)


class EntityDynamicTransposedView(APIView):
    """
    Retrieve Entity data dynamically transposed by Accounts or Cost Centers.
    Query Params:
        - `transpose_by`: 'account' or 'cost_center'
        - `format`: 'by_entity' or 'by_account'
    """
    

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, tenant_id=None):
        transpose_by = request.query_params.get('transpose_by', 'account')
        format_type = request.query_params.get('format', 'by_entity')

        if transpose_by not in ['account', 'cost_center']:
            return Response(
                {"error": "Invalid transpose_by value. Use 'account' or 'cost_center'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if format_type not in ['by_entity', 'by_account']:
            return Response(
                {"error": "Invalid format value. Use 'by_entity' or 'by_account'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        entities = Entity.objects.all(company__subdomain=tenant_id)
        results = self.get_effective_context_list(entities)

        if format_type == 'by_entity':
            return self.format_by_entity(results, transpose_by)
        else:
            return self.format_by_account_or_cost_center(results, transpose_by)

    def get_effective_context_list(self, entities):
        """
        Build the base data structure from entities.
        """
        results = []
        for entity in entities:
            accounts = entity.get_accounts()
            cost_centers = entity.get_cost_centers()
            
            account_data = AccountSerializer(accounts, many=True).data
            cost_center_data = CostCenterSerializer(cost_centers, many=True).data

            results.append({
                "entity_id": entity.id,
                "entity_name": entity.name,
                "accounts": account_data,
                "cost_centers": cost_center_data
            })
        return results

    def format_by_entity(self, results, transpose_by):
        """
        Format data by entity (rows are entities).
        """
        formatted_data = []

        for entity in results:
            row = {
                "entity_id": entity['entity_id'],
                "entity_name": entity['entity_name']
            }

            if transpose_by == 'account':
                for account in entity['accounts']:
                    row[account['name']] = account['balance']  # Example: Use balance as value
            elif transpose_by == 'cost_center':
                for cost_center in entity['cost_centers']:
                    row[cost_center['name']] = cost_center['description']  # Example: Use description as value

            formatted_data.append(row)

        return Response(formatted_data, status=status.HTTP_200_OK)

    def format_by_account_or_cost_center(self, results, transpose_by):
        """
        Format data with account or cost center names as columns.
        """
        transposed_data = {}

        if transpose_by == 'account':
            for entity in results:
                for account in entity['accounts']:
                    if account['name'] not in transposed_data:
                        transposed_data[account['name']] = {}
                    transposed_data[account['name']][entity['entity_name']] = account['balance']
        
        elif transpose_by == 'cost_center':
            for entity in results:
                for cost_center in entity['cost_centers']:
                    if cost_center['name'] not in transposed_data:
                        transposed_data[cost_center['name']] = {}
                    transposed_data[cost_center['name']][entity['entity_name']] = cost_center['description']

        # Transform the dictionary into a list of rows for Retool compatibility
        formatted_data = []
        for column_name, row_data in transposed_data.items():
            row = {"name": column_name, **row_data}
            formatted_data.append(row)

        return Response(formatted_data, status=status.HTTP_200_OK)

class EntityTreeView(generics.ListAPIView):
    #queryset = Company.objects.none()
    serializer_class = EntitySerializer
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        if hasattr(self.request, 'tenant'):
            if self.request.tenant == 'all':
                # Handle 'all' differently if needed, for example, return all entities or handle as not allowed
                return Entity.objects.all()
            else:
                # Assuming 'company_id' is still relevant, ensure it matches request.tenant as well for extra security
                company_id = self.kwargs['company_id']
                if str(self.request.tenant.id) == company_id:
                    return Entity.objects.filter(company_id=company_id)
                else:
                    return Entity.objects.none()  # Or handle as appropriate
        else:
            return Entity.objects.none()  # Or handle as appropriate

class ValidateRuleView(APIView):

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        """
        Endpoint to validate a rule and propose mock setup data and payload.
        """
        trigger_event = request.data.get("trigger_event")
        rule = request.data.get("rule")
        filter_conditions = request.data.get("filter_conditions")
        num_records = request.data.get("num_records", 10)  # Default to 10 records

        if not trigger_event or not rule:
            return Response(
                {"success": False, "error": "Missing required fields: trigger_event or rule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        
        
        try:
            # Validate the rule and generate mock data
            validation_result = validate_rule(trigger_event, rule, filter_conditions, num_records)

            # Format setupData
            setup_data = validation_result.get("setupData", {})
            setup_data_text = ""
            print('setup_data.items():', setup_data.items())
            for model_name, records in reversed(list(setup_data.items())):
                setup_data_text += f"# {model_name}\n"
                setup_data_text += "\n".join([f"cls.{model_name.lower()}_{i+1} = {record}" for i, record in enumerate(records)])
                setup_data_text += "\n\n"
            print('setup_data_text:', setup_data_text)
            # Format mockPayload
            mock_payload = validation_result.get("mockPayload", [])
            mock_payload_text = f"payload = [\n    " + ",\n    ".join([str(record) for record in mock_payload]) + "\n]"
            
            mock_filtered_payload = validation_result.get("filteredPayload", [])
            mock_filtered_payload_text = f"filtered_payload = [\n    " + ",\n    ".join([str(record) for record in mock_filtered_payload]) + "\n]"
            
            # Combine all output as JSON with Python-like syntax
            result = {
                "validation_result": f"Syntax Valid: {validation_result['validation']['syntax_valid']}\n"
                                     f"Special Functions: {', '.join(validation_result['validation']['special_functions'])}",
                "setup_data": setup_data_text.strip(),
                "mock_payload": mock_payload_text.strip(),
                "mock_filtered_payload": mock_filtered_payload_text.strip(),
            }

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

class ExecuteRuleView(APIView):

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    def post(self, request, tenant_id=None):
        """
        Endpoint to execute a rule in a sandboxed environment.
        """
        company_id = tenant_id
        setup_data = request.data.get("setup_data")
        payload = request.data.get("payload")
        rule = request.data.get("rule")

        print('company_id', company_id)        
        print('setup_data', setup_data) 
        print('payload', payload) 
        print('rule', rule) 
        
        # Parse setup_data and payload if they are strings

        if not company_id or not setup_data or not payload or not rule:
            return Response(
                {"success": False, "error": "Missing required fields: company_id, setup_data, payload, or rule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            execution_result = run_rule_in_sandbox(company_id, rule, setup_data, payload)
            return Response(execution_result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
class SubstitutionRuleViewSet(viewsets.ModelViewSet):
    """
    CRUD de regras de substituição (de‑para).
    """
    queryset = SubstitutionRule.objects.all()
    serializer_class = SubstitutionRuleSerializer
    

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        company = getattr(self.request, 'tenant', None)
        return super().get_queryset().filter(company=company)
    

class IntegrationRuleViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = IntegrationRule.objects.all()
    serializer_class = IntegrationRuleSerializer
    

    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        company = getattr(self.request, 'tenant', None)
        return super().get_queryset().filter(company=company)

    # Endpoint para executar uma regra específica (síncrono ou assíncrono)
    def run(self, request, pk=None):
        rule = self.get_object()
        payload = request.data.get("payload", {})
        if rule.use_celery:
            res = trigger_integration_event.delay(rule.company_id, rule.trigger_event, payload)
            return Response({"task_id": res.id}, status=status.HTTP_202_ACCEPTED)
        else:
            result = rule.run_rule(payload)
            return Response({"result": result}, status=status.HTTP_200_OK)

def _scrub_json(o):
    # Replace NaN/±Inf with None (valid JSON), recurse containers
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

class BulkImportAPIView(APIView):
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:

        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        up = request.FILES["file"]
        # compute sha256 (preserve file pointer)
        _bytes = up.read()
        file_sha256 = hashlib.sha256(_bytes).hexdigest()
        size = len(_bytes)
        up.seek(0)

        # build sheets (your existing logic)
        book = pd.read_excel(up, sheet_name=None)
        sheets = []
        for model_name, df in book.items():
            if model_name == "References":
                continue
            df = df.replace([np.inf, -np.inf], np.nan)
            df = df.where(df.notna(), None)        # NaN/NaT -> None
            rows = df.dropna(how="all").to_dict(orient="records")
            sheets.append({"model": model_name, "rows": rows})

        commit = _to_bool(request.data.get("commit"), default=False)
        use_celery = _to_bool(request.data.get("use_celery"), default=False)

        company_id = request.data.get("company_id") or getattr(request.user, "company_id", None)
        if not company_id:
            return Response({"error": "No company defined"}, status=400)
        
        file_meta = {"sha256": file_sha256, "size": size, "filename": getattr(up, "name", None)}
        
        # Build import_metadata with filename for notes
        import_metadata = {
            'source': 'Import',
            'function': 'BulkImportAPIView.post',
            'filename': file_meta.get('filename'),
        }
        
        if use_celery:
            from .etl_tasks import process_import_template_task
            async_res = process_import_template_task.delay(
                company_id=company_id,
                sheets=sheets,
                commit=commit,
                file_meta=file_meta
            )
            return Response({
                "task_id": async_res.id,
                "message": "Import scheduled",
                "status_url": f"/api/tasks/{async_res.id}/status/"
            }, status=status.HTTP_202_ACCEPTED)

        # Synchronous
        result = execute_import_job(company_id, sheets, commit, import_metadata=import_metadata)

        # Final safety: scrub any NaN/±Inf that may have been produced downstream
        result = _scrub_json(result)

        http_status = status.HTTP_200_OK if result.get("committed") else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


# ============================================================================
# ETL PIPELINE VIEWS
# ============================================================================

class ImportTransformationRuleViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    """
    CRUD endpoints for ImportTransformationRule.
    
    GET /api/{tenant_id}/etl/transformation-rules/
    POST /api/{tenant_id}/etl/transformation-rules/
    GET /api/{tenant_id}/etl/transformation-rules/{id}/
    PUT /api/{tenant_id}/etl/transformation-rules/{id}/
    DELETE /api/{tenant_id}/etl/transformation-rules/{id}/
    """
    queryset = ImportTransformationRule.objects.all()
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ImportTransformationRuleListSerializer
        return ImportTransformationRuleSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by is_active if provided
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=_to_bool(is_active))
        # Filter by target_model if provided
        target_model = self.request.query_params.get('target_model')
        if target_model:
            qs = qs.filter(target_model__iexact=target_model)
        return qs.order_by('execution_order', 'name')
    
    @action(detail=False, methods=['get'])
    def available_models(self, request, tenant_id=None):
        """Return list of valid target models."""
        from .tasks import MODEL_APP_MAP
        return Response({
            'models': list(MODEL_APP_MAP.keys())
        })


class ETLPipelineLogViewSet(ScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoints for ETL pipeline logs.
    
    GET /api/{tenant_id}/etl/logs/
    GET /api/{tenant_id}/etl/logs/{id}/
    """
    queryset = ETLPipelineLog.objects.all()
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ETLPipelineLogListSerializer
        return ETLPipelineLogSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        # Filter by is_preview if provided
        is_preview = self.request.query_params.get('is_preview')
        if is_preview is not None:
            qs = qs.filter(is_preview=_to_bool(is_preview))
        return qs.order_by('-started_at')


class ETLPipelinePreviewView(APIView):
    """
    Preview ETL pipeline transformation without committing.
    
    POST /api/{tenant_id}/etl/preview/
    
    Request:
        - file: Excel file (multipart/form-data)
    
    Response:
        - success: bool
        - summary: {sheets_found, sheets_processed, etc.}
        - data: {model_name: {row_count, rows, sample_columns}}
        - errors: [{type, message, stage, ...}]
        - warnings: [{type, message, ...}]
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided. Upload an Excel file.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        company_id = request.data.get('company_id') or tenant_id
        if not company_id:
            return Response(
                {'error': 'No company_id provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .etl_service import ETLPipelineService
        from .etl_tasks import process_etl_file_task, process_etl_batch_task
        import json
        import hashlib
        
        # Check if multiple files or single file
        files = request.FILES.getlist('file') if 'file' in request.FILES else []
        use_celery = request.data.get('use_celery', 'false').lower() in ('true', '1', 'yes')
        
        # Single file processing
        if len(files) == 1:
            file = files[0]
        
        # Extract auto_create_journal_entries from request (can be JSON string or dict)
        auto_create_journal_entries = None
        if 'auto_create_journal_entries' in request.data:
            auto_create_val = request.data.get('auto_create_journal_entries')
            if isinstance(auto_create_val, str):
                try:
                    auto_create_journal_entries = json.loads(auto_create_val)
                except json.JSONDecodeError:
                    auto_create_journal_entries = {}
            elif isinstance(auto_create_val, dict):
                auto_create_journal_entries = auto_create_val
        
        # Extract row_limit from request (default: 10, 0 = process all rows)
        row_limit = 10  # Default for testing
        if 'row_limit' in request.data:
            try:
                row_limit_val = request.data.get('row_limit')
                if isinstance(row_limit_val, str):
                    row_limit = int(row_limit_val)
                elif isinstance(row_limit_val, (int, float)):
                    row_limit = int(row_limit_val)
            except (ValueError, TypeError):
                row_limit = 10  # Fallback to default
        
        service = ETLPipelineService(
            company_id=int(company_id),
            file=file,
            commit=False,  # Preview mode
            auto_create_journal_entries=auto_create_journal_entries,
            row_limit=row_limit
        )
        
        result = service.execute()
        result = _scrub_json(result)
        
        http_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


class ETLPipelineExecuteView(APIView):
    """
    Execute ETL pipeline and commit to database.
    
    POST /api/{tenant_id}/etl/execute/
    
    Request:
        - file: Excel file (multipart/form-data)
    
    Response:
        - success: bool
        - summary: {sheets_found, sheets_processed, etc.}
        - import_result: {results, committed, etc.}
        - errors: [{type, message, stage, ...}]
        - warnings: [{type, message, ...}]
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided. Upload an Excel file.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        company_id = request.data.get('company_id') or tenant_id
        if not company_id:
            return Response(
                {'error': 'No company_id provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from .etl_service import ETLPipelineService
        from .etl_tasks import process_etl_file_task, process_etl_batch_task
        import json
        import hashlib
        
        # Check if multiple files or single file
        files = request.FILES.getlist('file') if 'file' in request.FILES else []
        use_celery = request.data.get('use_celery', 'false').lower() in ('true', '1', 'yes')
        
        # Single file processing
        if len(files) == 1:
            file = files[0]
        
        # Extract auto_create_journal_entries from request (can be JSON string or dict)
        auto_create_journal_entries = None
        if 'auto_create_journal_entries' in request.data:
            auto_create_val = request.data.get('auto_create_journal_entries')
            if isinstance(auto_create_val, str):
                try:
                    auto_create_journal_entries = json.loads(auto_create_val)
                except json.JSONDecodeError:
                    auto_create_journal_entries = {}
            elif isinstance(auto_create_val, dict):
                auto_create_journal_entries = auto_create_val
        
        # Extract row_limit from request (default: 10, 0 = process all rows)
        row_limit = 10  # Default for testing
        if 'row_limit' in request.data:
            try:
                row_limit_val = request.data.get('row_limit')
                if isinstance(row_limit_val, str):
                    row_limit = int(row_limit_val)
                elif isinstance(row_limit_val, (int, float)):
                    row_limit = int(row_limit_val)
            except (ValueError, TypeError):
                row_limit = 10  # Fallback to default
        
        service = ETLPipelineService(
            company_id=int(company_id),
            file=file,
            commit=True,  # Execute mode
            auto_create_journal_entries=auto_create_journal_entries,
            row_limit=row_limit
        )
        
        result = service.execute()
        result = _scrub_json(result)
        
        http_status = status.HTTP_200_OK if result.get('success') else status.HTTP_400_BAD_REQUEST
        return Response(result, status=http_status)


class ETLPipelineAnalyzeView(APIView):
    """
    Analyze an Excel file and suggest transformation rules.
    
    POST /api/{tenant_id}/etl/analyze/
    
    Request:
        - file: Excel file (multipart/form-data)
    
    Response:
        - sheets: [{name, columns, row_count, sample_rows}]
        - suggestions: [{sheet_name, suggested_target_model, suggested_mappings}]
    """
    
    if settings.AUTH_OFF:
        permission_classes = []
    else:
        permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, tenant_id=None):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided. Upload an Excel file.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        try:
            xls = pd.read_excel(file, sheet_name=None)
        except Exception as e:
            return Response(
                {'error': f'Failed to parse Excel file: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        sheets_info = []
        for sheet_name, df in xls.items():
            # Clean up dataframe
            df = df.dropna(how='all')
            
            columns = [str(col) for col in df.columns]
            row_count = len(df)
            
            # Get sample rows (first 5)
            sample_rows = []
            for idx, row in df.head(5).iterrows():
                sample_row = {}
                for col in columns:
                    val = row.get(col)
                    if pd.isna(val):
                        val = None
                    elif isinstance(val, (np.integer, np.floating)):
                        val = float(val) if np.isnan(val) == False else None
                    else:
                        val = str(val) if val is not None else None
                    sample_row[col] = val
                sample_rows.append(sample_row)
            
            sheets_info.append({
                'name': sheet_name,
                'columns': columns,
                'row_count': row_count,
                'sample_rows': sample_rows,
            })
        
        # Check for existing transformation rules
        company_id = request.data.get('company_id') or tenant_id
        existing_rules = []
        if company_id:
            existing_rules = list(
                ImportTransformationRule.objects.filter(
                    company_id=company_id,
                    is_active=True
                ).values('source_sheet_name', 'target_model', 'name')
            )
        
        result = _scrub_json({
            'sheets': sheets_info,
            'existing_rules': existing_rules,
            'file_name': getattr(file, 'name', 'unknown'),
        })
        
        return Response(result, status=status.HTTP_200_OK)