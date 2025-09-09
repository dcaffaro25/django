# NORD/multitenancy/views.py
from rest_framework.views import APIView
from django.contrib.auth import authenticate, login, logout
from rest_framework import views, viewsets, generics, status, serializers
from rest_framework.response import Response
from .models import CustomUser, Company, Entity, IntegrationRule, SubstitutionRule
from .mixins import ScopedQuerysetMixin
from .serializers import CustomUserSerializer, CompanySerializer, EntitySerializer, UserLoginSerializer, IntegrationRuleSerializer, EntityMiniSerializer, ChangePasswordSerializer, UserCreateSerializer, PasswordResetForceSerializer, SubstitutionRuleSerializer
from .api_utils import create_csv_response, create_excel_response
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from accounting.serializers import AccountSerializer, CostCenterSerializer
from .formula_engine import validate_rule, run_rule_in_sandbox
from rest_framework.authtoken.models import Token
from django.core.mail import send_mail
from django.conf import settings
from .tasks import send_user_invite_email, send_user_email
from django.utils import timezone
from datetime import timedelta
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from multitenancy.tasks import dispatch_import, trigger_integration_event
from core.utils.json_sanitize import json_nullsafe

import pandas as pd


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
    permission_classes = [permissions.IsAdminUser]  # or AllowAny if self-service
    
    
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

class CustomUserViewSet(viewsets.ModelViewSet):
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

    def get_queryset(self):
        #if hasattr(self.request, 'tenant'):
        #    if self.request.tenant == 'all':
        #        return Company.objects.all()
        #    else:
        #        return Company.objects.filter(pk=self.request.tenant.pk)
        #else:
        #    return Company.objects.none()  # Or handle as appropriate
        return Company.objects.all()



class EntityMiniViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Entity.objects.all()
    serializer_class = EntityMiniSerializer

class EntityViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

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

    def get_queryset(self):
        company = getattr(self.request, 'tenant', None)
        return super().get_queryset().filter(company=company)
    

class IntegrationRuleViewSet(ScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = IntegrationRule.objects.all()
    serializer_class = IntegrationRuleSerializer

    def get_queryset(self):
        company = getattr(self.request, 'tenant', None)
        return super().get_queryset().filter(company=company)

    # Endpoint para executar uma regra específica (síncrono ou assíncrono)
    def run(self, request, pk=None):
        rule = self.get_object()
        payload = request.data.get("payload", {})
        if rule.use_celery:
            res = trigger_integration_event.delay(rule.company_id, rule.triggers, payload)
            return Response({"task_id": res.id}, status=status.HTTP_202_ACCEPTED)
        else:
            result = rule.run_rule(payload)
            return Response({"result": result}, status=status.HTTP_200_OK)

class BulkImportAPIView(APIView):
    """
    Endpoint de importação em massa.
    Divide o DataFrame em chunks e utiliza Celery se use_celery=True.
    """
    def post(self, request, *args, **kwargs):
        file = request.FILES['file']
        xls = pd.read_excel(file, sheet_name=None)
        commit = request.data.get('commit', False)#getattr(request, 'commit', False)
        company = getattr(request, 'tenant', None)
        company_id = request.data.get('company_id')
        if not company_id and hasattr(request.user, 'company_id'):
            company_id = request.user.company_id
        
        if not company_id:
            return Response({"error": "No company defined"}, status=400)
        
        use_celery = request.data.get('use_celery', False)
        responses = []
        for model_name, df in xls.items():
            if model_name == "References":
                continue
            rows = df.dropna(how='all').to_dict(orient="records")
            if use_celery:
                # dispara async
                async_res = dispatch_import.delay(company_id, model_name, rows, commit=commit, use_celery=True)
                responses.append({"model": model_name, "task_id": async_res.id})
            else:
                # processa síncrono
                result = dispatch_import(company_id, model_name, rows, commit=commit, use_celery=False)
                responses.append({"model": model_name, "result": result})
        return Response({"imports": json_nullsafe(responses)}, status=status.HTTP_202_ACCEPTED)