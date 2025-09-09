# models.py
from datetime import date
from django.db import models
from django.utils.timezone import now
from django.core.exceptions import ValidationError
from multitenancy.models import Company
from decimal import Decimal
from datetime import datetime, timedelta, date
import re
from multitenancy.models import BaseModel, TenantAwareBaseModel


class Position(TenantAwareBaseModel):
    """
    Represents the position of an employee (e.g. Developer, Manager).
    """
    title = models.CharField(max_length=100, unique=True)
    description = models.TextField(null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)
    hierarchy_level = models.PositiveIntegerField(null=True, blank=True)
    min_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def clean(self):
        if self.min_salary and self.max_salary and self.min_salary > self.max_salary:
            raise ValidationError("Minimum salary cannot exceed maximum salary.")

    def __str__(self):
        return f"{self.title}"

class Employee(TenantAwareBaseModel):
    """
    Basic employee model.
    """
    CPF = models.CharField(max_length=14, unique=True)
    name = models.CharField(max_length=255)
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, null=True, related_name='employees')
    hire_date = models.DateField()
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    vacation_days = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    is_active = models.BooleanField(default=True)

    def clean(self):
        """
        Validate that the employee's salary falls between position min/max, if applicable.
        """
        if self.position:
            if self.position.min_salary and self.salary < self.position.min_salary:
                raise ValidationError(
                    f"Salary must be at least {self.position.min_salary} for position '{self.position.title}'."
                )
            if self.position.max_salary and self.salary > self.position.max_salary:
                raise ValidationError(
                    f"Salary cannot exceed {self.position.max_salary} for position '{self.position.title}'."
                )

    def accrued_vacation_days(self):
        worked_days = (now().date() - self.hire_date).days
        # Example: up to 30 days per year, proportionally
        return min((worked_days / 365) * 30, 30)

    def __str__(self):
        return f"{self.name}"

class TimeTracking(TenantAwareBaseModel):
    """
    Tracks attendance, hours worked, leaves, etc. for a given employee & month.
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected')
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    month_date = models.DateField(help_text="First day of that month.")
    
    total_hours_worked = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    total_overtime_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    overtime_hours_paid = models.DecimalField(max_digits=7, decimal_places=2, default=0,
                                             help_text="Overtime hours paid this month.")
    days_present = models.PositiveIntegerField(default=0)
    days_absent = models.PositiveIntegerField(default=0)
    leave_days = models.PositiveIntegerField(default=0)
    effective_hours = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    bank_hours_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                             help_text="Calculated bank hours balance for this month.")

    vacation_start_date = models.DateField(null=True, blank=True)
    vacation_end_date = models.DateField(null=True, blank=True)
    vacation_days_used = models.PositiveIntegerField(default=0)

    absence_reason = models.CharField(max_length=255, null=True, blank=True)

    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        unique_together = ('employee', 'month_date')
        verbose_name = 'Employee Attendance'
        verbose_name_plural = 'Employee Attendances'

    def clean(self):
        if (self.total_hours_worked < 0 or
            self.total_overtime_hours < 0 or
            self.overtime_hours_paid < 0):
            raise ValidationError("Hours worked, overtime hours, and paid overtime cannot be negative.")

        if (self.days_present < 0 or
            self.days_absent < 0 or
            self.leave_days < 0):
            raise ValidationError("Day counts cannot be negative.")

    def get_previous_month_balance(self):
        """
        Fetch the bank hours from the previous month.
        """
        if isinstance(self.month_date, str):
            parsed_date = datetime.strptime(self.month_date, "%Y-%m-%d").date()
        else:
            # Assume it's already a date/datetime
            parsed_date = self.month_date
        previous_month = (parsed_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        try:
            prev_record = TimeTracking.objects.get(employee=self.employee, month_date=previous_month)
            return prev_record.bank_hours_balance
        except TimeTracking.DoesNotExist:
            return Decimal('0.00')

    def calculate_bank_hours_balance(self):
        """
        Add net overtime to last month's bank hours.
        """
        previous_balance = self.get_previous_month_balance()
        net_overtime = self.total_overtime_hours - self.overtime_hours_paid
        return previous_balance + net_overtime

    def calculate_effective_hours(self):
        average_daily_hours = Decimal('8.00')
        return (self.days_present * average_daily_hours) + self.total_overtime_hours

    def save(self, *args, **kwargs):
        self.bank_hours_balance = self.calculate_bank_hours_balance()
        self.effective_hours = self.calculate_effective_hours()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.name} - {self.month_date:%b %Y} - {self.total_hours_worked} hrs"


class KPI(TenantAwareBaseModel):
    """
    Stores KPI name & value for an employee.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    month_date = models.DateField(help_text="First day of that month.")
    value = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.employee.name} - {self.month_date:%b %Y} - {self.name}"

class Bonus(TenantAwareBaseModel):
    """
    Bonus calculation is formula-based, referencing KPI values.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    calculation_formula = models.TextField(null=True, blank=True)  # e.g. "0.1 * KPI_Performance + 0.05 * KPI_Attendance"
    value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def calculate_bonus(self):
        from hr.models import KPI
        # Gather KPI data
        kpis = {f"KPI_{kpi.name}": kpi.value for kpi in KPI.objects.filter(employee=self.employee)}
        try:
            formula_eval = self.calculation_formula
            for key, val in kpis.items():
                formula_eval = formula_eval.replace(key, str(val))
            self.value = eval(formula_eval)  # be sure to sanitize or limit scope
        except (KeyError, SyntaxError, NameError):
            raise ValueError("Invalid formula or missing KPI data.")
        self.save()

    def __str__(self):
        return f"Bonus for {self.employee.name}"

class RecurringAdjustment(TenantAwareBaseModel):
    """
    Additional or Deduction items that may be included in payroll calculation.
    """
    TYPE_ADDITIONAL = 'additional'
    TYPE_DEDUCTION = 'deduction'
    TYPE_CHOICES = [
        (TYPE_ADDITIONAL, 'Additional'),
        (TYPE_DEDUCTION, 'Deduction'),
    ]

    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('custom', 'Custom Rule'),
    ]

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='recurring_adjustments')
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    base_for_inss = models.BooleanField(default=False)
    base_for_fgts = models.BooleanField(default=False)
    base_for_irpf = models.BooleanField(default=False)
    calculation_formula = models.TextField(
        null=True,
        blank=True,
        help_text="E.g. '(days_present * 8) + total_overtime_hours'"
    )
    employer_cost_formula = models.TextField(
        null=True,
        blank=True,
        help_text="E.g. 'adjustment_value * 0.2'"
    )
    priority = models.PositiveIntegerField(default=0)

    # If relevant accounts need to be linked
    default_account = models.ManyToManyField('accounting.Account', blank=True, default=None)

    def is_active(self):
        today_date = now().date()
        return self.start_date <= today_date and (not self.end_date or self.end_date >= today_date)

    def preprocess_formula(self, formula, context: dict) -> str:
        """
        Replaces placeholders like [days_present] with context['days_present'] etc.
        Also handles semicolons, decimal commas, etc.
        """
        if not formula:
            raise ValueError("No formula defined for adjustment calculation.")

        def replace_field(match):
            field_name = match.group(1)
            if field_name not in context:
                raise ValueError(f"Invalid field {field_name} in formula.")
            return str(context[field_name])

        # Replace e.g. [field] => context's value
        formula = re.sub(r'\[([a-zA-Z_]+)\]', replace_field, formula)

        # Replace semicolons with commas
        formula = formula.replace(';', ',')

        # Replace comma as decimal separator with dot
        formula = re.sub(r'(\d+),(\d+)', r'\1.\2', formula)

        return formula

    def calculate_adjustment(self, base_salary, attendance=None):
        if not self.calculation_formula:
            raise ValueError("No formula defined for adjustment calculation.")
        if attendance is None:
            raise ValueError("No attendance object provided (or we are simulating with dummy).")

        context = {
            'base_salary': float(base_salary),
            'days_present': float(attendance.days_present),
            'days_absent': float(attendance.days_absent),
            'leave_days': float(attendance.leave_days),
            'total_days': float(attendance.days_present + attendance.days_absent + attendance.leave_days),
            'total_hours_worked': float(attendance.total_hours_worked),
            'total_overtime_hours': float(attendance.total_overtime_hours),
            'overtime_hours_paid': float(attendance.overtime_hours_paid),
            'bank_hours_balance': float(attendance.bank_hours_balance),
            'vacation_days_used': float(attendance.vacation_days_used),
            # Built-ins that might be allowed
            'min': min,
            'max': max,
            'abs': abs,
        }
        safe_formula = self.preprocess_formula(self.calculation_formula, context)
        try:
            result = Decimal(eval(safe_formula, {"__builtins__": None}, context))
            return result
        except Exception as e:
            raise ValueError(f"Error evaluating formula {safe_formula}: {e}")

    def calculate_employer_cost(self, adjustment_value, attendance=None) -> Decimal:
        """
        For advanced cases, if we store a separate formula for the employer portion.
        """
        if not self.employer_cost_formula:
            return Decimal('0.00')
        context = {
            'adjustment_value': float(adjustment_value),
            'days_present': float(attendance.days_present) if attendance else 0,
            'days_absent': float(attendance.days_absent) if attendance else 0,
            'total_hours_worked': float(attendance.total_hours_worked) if attendance else 0,
            # etc.
            'min': min,
            'max': max,
            'abs': abs,
        }
        safe_formula = self.preprocess_formula(self.employer_cost_formula, context)
        try:
            return Decimal(eval(safe_formula, {"__builtins__": None}, context))
        except Exception as e:
            raise ValueError(f"Error evaluating employer cost formula: {e}")

    def __str__(self):
        return f"{self.name} ({self.type}) - {self.employee}"

class Payroll(TenantAwareBaseModel):
    """
    Actual payroll record for a single employee, single date (month).
    """
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_PAID = 'paid'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_PAID, 'Paid')
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    pay_date = models.DateField()

    # Basic fields
    gross_salary = models.DecimalField(max_digits=10, decimal_places=2)
    inss_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    irrf_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    fgts = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    bank_hours = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    absence_deduction = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    adjustment_details = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)

    class Meta:
        unique_together = ('employee', 'pay_date')

    def calculate_absence_deductions(self):
        # Currently just uses self.absence_deduction
        return self.absence_deduction

    def calculate_adjustments(self, attendance=None):
        """
        Sum up the additions/deductions from RecurringAdjustment objects.
        Return (additions, deductions, details)
        """
        # Grab all active adjustments for this date
        active_adj = self.employee.recurring_adjustments.filter(
            start_date__lte=self.pay_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.pay_date)
        )

        additions = Decimal('0.00')
        deductions = Decimal('0.00')
        details = {}

        # Possibly consider absence-based deduction
        absence_deductions = self.calculate_absence_deductions()
        if absence_deductions != 0:
            details['absence_deductions'] = {
                'type': 'deduction',
                'value': float(absence_deductions),
                'base_for_inss': True,
                'base_for_fgts': True,
                'base_for_irpf': True
            }
            deductions += Decimal(absence_deductions)

        for adj in active_adj:
            # Evaluate the formula
            value = adj.calculate_adjustment(self.employee.salary, attendance=attendance)
            if adj.type == RecurringAdjustment.TYPE_ADDITIONAL:
                additions += value
            else:
                deductions += value

            details[adj.name] = {
                'type': adj.type,
                'value': float(value),
                'base_for_inss': adj.base_for_inss,
                'base_for_fgts': adj.base_for_fgts,
                'base_for_irpf': adj.base_for_irpf,
            }

        return additions, deductions, details

    def calculate_inss(self, attendance=None):
        # Start from base + adjustments that are flagged base_for_inss
        inss_base = self.calculate_adjustment_base(flag='base_for_inss', attendance=attendance)
        brackets = [
            (1412.00, Decimal('0.075')),
            (2666.68, Decimal('0.09')),
            (4000.03, Decimal('0.12')),
            (7786.02, Decimal('0.14'))
        ]
        total_inss = Decimal('0.00')
        remaining = inss_base
        for limit, rate in brackets:
            if remaining > limit:
                total_inss += Decimal(limit) * rate
                remaining -= Decimal(limit)
            else:
                total_inss += remaining * rate
                break
        return min(total_inss, Decimal('908.86'))

    def calculate_irrf(self, inss, attendance=None):
        # base IRPF includes adjustments flagged for irpf, minus inss
        irpf_base = self.calculate_adjustment_base(flag='base_for_irpf', attendance=attendance) - inss
        brackets = [
            (2259.20, Decimal('0.0'), Decimal('0.0')),
            (2826.65, Decimal('0.075'), Decimal('169.44')),
            (3751.05, Decimal('0.15'), Decimal('381.44')),
            (4664.68, Decimal('0.225'), Decimal('662.77')),
            (Decimal('inf'), Decimal('0.275'), Decimal('896.00'))
        ]
        total_irrf = Decimal('0.00')
        for limit, rate, deduction in brackets:
            if irpf_base <= limit:
                total_irrf = max((irpf_base * rate) - deduction, Decimal('0.00'))
                break
        return total_irrf

    def calculate_fgts(self, attendance=None):
        # base FGTS includes adjustments flagged for fgts
        fgts_base = self.calculate_adjustment_base('base_for_fgts', attendance=attendance)
        return fgts_base * Decimal('0.08')

    def calculate_adjustment_base(self, flag: str, attendance=None) -> Decimal:
        """
        Builds a 'base' for applying inss, fgts, irpf by adding or removing
        adjustments that are flagged for that category.
        """
        base = Decimal(self.employee.salary)

        # Reuse the same logic from calculate_adjustments, but only sum the flagged items
        active_adj = self.employee.recurring_adjustments.filter(
            start_date__lte=self.pay_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.pay_date)
        )

        # Also factor in self.absence_deduction if it's flagged for that base
        # (We do that by either re-checking or referencing the same logic.)
        # Simpler approach: recalc everything. Then add up only those flagged. 
        # This is a reference approach:

        for adj in active_adj:
            if getattr(adj, flag, False):
                adj_value = adj.calculate_adjustment(self.employee.salary, attendance=attendance)
                if adj.type == RecurringAdjustment.TYPE_ADDITIONAL:
                    base += adj_value
                else:
                    base -= adj_value

        # Also consider absence if flagged:
        if flag in ['base_for_inss', 'base_for_fgts', 'base_for_irpf']:
            # if we are doping a minimal approach, we check details or just do:
            if self.absence_deduction != 0:
                # Suppose we always treat absence as 'deduction' so subtract
                base -= Decimal(self.absence_deduction)

        return max(base, Decimal('0.00'))

    def recalculate_payroll(self, attendance=None, simulate=False):
        """
        Recomputes all payroll amounts. If simulate=True, do not .save() at the end.
        If attendance=None and simulate=True, create a dummy attendance object.
        """
        # If simulating, but no attendance, create a dummy
        if simulate and attendance is None:
            from hr.models import TimeTracking  # self import
            attendance = TimeTracking(
                employee=self.employee,
                month_date=self.pay_date,
                days_present=20,
                days_absent=0,
                leave_days=0,
                total_hours_worked=Decimal('160.0'),
                total_overtime_hours=Decimal('0.0'),
                overtime_hours_paid=Decimal('0.0'),
                bank_hours_balance=Decimal('0.0'),
            )

        additions, deductions, details = self.calculate_adjustments(attendance=attendance)
        self.adjustment_details = details

        self.inss_deduction = self.calculate_inss(attendance=attendance)
        self.fgts = self.calculate_fgts(attendance=attendance)
        self.irrf_deduction = self.calculate_irrf(self.inss_deduction, attendance=attendance)

        # net = salary + additions - deductions - inss - irrf
        self.net_salary = (
            Decimal(self.employee.salary) + additions - deductions
            - self.inss_deduction - self.irrf_deduction
        )

        if not simulate:
            self.save()

    @staticmethod
    def generate_monthly_payroll(company, employees=None, pay_date=None, simulate=False):
        """
        If simulate=True, we skip final .save().
        If employees=None, fetch all active in the company.
        """
        if not pay_date:
            pay_date = date.today()
        if employees is None:
            employees = Employee.objects.filter(company=company, is_active=True)

        payroll_entries = []
        for emp in employees:
            # skip if payroll exists
            if Payroll.objects.filter(employee=emp, pay_date=pay_date).exists():
                continue

            p = Payroll(
                employee=emp,
                company=company,
                pay_date=pay_date,
                gross_salary=emp.salary,
                status=Payroll.STATUS_PENDING
            )

            if simulate:
                p.recalculate_payroll(attendance=None, simulate=True)
            else:
                # if not simulate, try real TimeTracking
                try:
                    attendance = TimeTracking.objects.get(employee=emp, month_date=pay_date)
                except TimeTracking.DoesNotExist:
                    # skip or create partial logic
                    continue
                p.recalculate_payroll(attendance=attendance, simulate=False)

            if not simulate:
                p.save()

            payroll_entries.append(p)

        return payroll_entries

    def __str__(self):
        return f"{self.employee.name} - {self.pay_date} - {self.status}"