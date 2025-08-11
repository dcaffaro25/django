# views.py
from django.db import transaction
from rest_framework import viewsets, filters, status
from .models import Position, Employee, TimeTracking, KPI, Bonus, Payroll, RecurringAdjustment
from multitenancy.models import Company
from multitenancy.formula_engine import trigger_rule_event

from .serializers import (
    PositionSerializer, EmployeeSerializer, TimeTrackingSerializer,
    KPISerializer, BonusSerializer, PayrollSerializer, PayrollRecalculationSerializer,
    PayrollGenerationSerializer, RecurringAdjustmentSerializer, PayrollBulkStatusSerializer
)


from rest_framework.decorators import action
from rest_framework.response import Response




class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer

class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('position')
    serializer_class = EmployeeSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'CPF', 'position__title']
    ordering_fields = ['hire_date', 'salary']

class TimeTrackingViewSet(viewsets.ModelViewSet):
    queryset = TimeTracking.objects.all()
    serializer_class = TimeTrackingSerializer

    def perform_create(self, serializer):
        # We can do an atomic block if desired
        with transaction.atomic():
            serializer.save()

class KPIViewSet(viewsets.ModelViewSet):
    queryset = KPI.objects.all()
    serializer_class = KPISerializer

class BonusViewSet(viewsets.ModelViewSet):
    queryset = Bonus.objects.all()
    serializer_class = BonusSerializer

class PayrollViewSet(viewsets.ModelViewSet):
    queryset = Payroll.objects.all()
    serializer_class = PayrollSerializer

    @action(detail=False, methods=['post'], url_path='recalculate')
    def recalculate(self, request, tenant_id=None):
        """
        POST { "payroll_ids": [1, 2, 3] }
        Recalculate these payrolls (DB commits).
        """
        serializer = PayrollRecalculationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payroll_ids = serializer.validated_data['payroll_ids']

        for pay_id in payroll_ids:
            try:
                p = Payroll.objects.get(id=pay_id)
            except Payroll.DoesNotExist:
                continue  # or raise
            # Attempt to fetch real attendance:
            try:
                attendance = TimeTracking.objects.get(
                    employee=p.employee,
                    month_date=p.pay_date
                )
            except TimeTracking.DoesNotExist:
                attendance = None
            p.recalculate_payroll(attendance=attendance, simulate=False)
        return Response({"message": "Payroll(s) recalculated successfully."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='generate-monthly')
    def generate_monthly(self, request, tenant_id=None):
        """
        POST { "company_id": 1, "employee_ids": [...], "pay_date": "2025-02-01", "simulate": true/false }
        """
        serializer = PayrollGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        company_id = serializer.validated_data['company_id']
        employee_ids = serializer.validated_data.get('employee_ids', [])
        pay_date = serializer.validated_data.get('pay_date')
        simulate = serializer.validated_data.get('simulate', False)

        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return Response({"error": "Invalid company ID."}, status=status.HTTP_400_BAD_REQUEST)

        employees = Employee.objects.filter(id__in=employee_ids, is_active=True) if employee_ids else None

        # We'll do an atomic block if we want partial writes only if not simulate
        if simulate:
            # Just do everything in memory, no DB commits
            payroll_entries = Payroll.generate_monthly_payroll(company, employees, pay_date, simulate=True)
            # Build a small response
            result_data = PayrollSerializer(payroll_entries, many=True).data
            return Response({
                "message": "[SIMULATION] Payroll generation completed. No records committed.",
                "payroll_entries": result_data
            }, status=status.HTTP_200_OK)
        else:
            with transaction.atomic():
                payroll_entries = Payroll.generate_monthly_payroll(company, employees, pay_date, simulate=False)

                # For demonstration, we might trigger a rule after generation
                # e.g. if your domain says "auto-approve"? Or do we do a separate event?
                # e.g. trigger_rule_event(company.id, "payroll_approved", ... ) ?

                result_data = PayrollSerializer(payroll_entries, many=True).data
                return Response({
                    "message": "Payroll generated successfully.",
                    "payroll_ids": [p.id for p in payroll_entries],
                    "entries": result_data
                }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='bulk-update-status')
    def bulk_update_status(self, request, tenant_id=None):
        """
        Bulk update the status of multiple payroll entries.
        {
            "payroll_ids": [...],
            "new_status": "approved",
            "simulate": true/false
        }
        """
        serializer = PayrollBulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payroll_ids = serializer.validated_data['payroll_ids']
        new_status = serializer.validated_data['new_status']
        simulate = serializer.validated_data.get('simulate', False)

        payroll_qs = Payroll.objects.filter(id__in=payroll_ids)
        if payroll_qs.count() != len(payroll_ids):
            found_ids = set(payroll_qs.values_list('id', flat=True))
            missing = [i for i in payroll_ids if i not in found_ids]
            return Response(
                {"detail": f"Some Payroll IDs not found: {missing}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # We'll do minimal data for the rule event
        # (like gross_salary, maybe net_salary, etc.)
        rule_payload = []

        if simulate:
            # purely in memory
            updated = []
            for payroll in payroll_qs:
                new_obj = Payroll(
                    id=payroll.id,
                    employee=payroll.employee,
                    company=payroll.company,
                    pay_date=payroll.pay_date,
                    gross_salary=payroll.gross_salary,
                    net_salary=payroll.net_salary,
                    status=new_status
                )
                updated.append(new_obj)
                # build rule info if new_status=approved
                if new_status == Payroll.STATUS_APPROVED:
                    rule_payload.append({
                        "id": payroll.id,
                        "gross_salary": str(payroll.gross_salary),
                    })
            # We do not save nor do a transaction rollback,
            # we simply do not do any DB commit
            updated_serialized = PayrollSerializer(updated, many=True).data
            return Response({
                "detail": "[SIMULATION] Bulk status update performed. No DB commit.",
                "updated_entries": updated_serialized
            }, status=status.HTTP_200_OK)
        else:
            # real commit scenario
            with transaction.atomic():
                updated_payrolls = []
                for payroll in payroll_qs:
                    payroll.status = new_status
                    payroll.save(update_fields=["status"])
                    updated_payrolls.append(payroll)

                # If new_status=approved => we might call the rule once with entire group
                if new_status == Payroll.STATUS_APPROVED:
                    rule_payload = [
                        {
                            "id": p.id,
                            "gross_salary": str(p.gross_salary),
                        }
                        for p in updated_payrolls
                    ]
                    trigger_rule_event(
                        company=updated_payrolls[0].company.id,  # assume all same
                        event_name="payroll_approved",
                        payload=rule_payload
                    )

                return Response({
                    "detail": f"Status updated to '{new_status}' for {len(updated_payrolls)} payroll(s).",
                    "updated_ids": [p.id for p in updated_payrolls],
                }, status=status.HTTP_200_OK)

class RecurringAdjustmentViewSet(viewsets.ModelViewSet):
    queryset = RecurringAdjustment.objects.all()
    serializer_class = RecurringAdjustmentSerializer