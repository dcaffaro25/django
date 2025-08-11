# serializers.py
from rest_framework import serializers
from .models import Position, Employee, TimeTracking, KPI, Bonus, Payroll, RecurringAdjustment
from multitenancy.serializers import CompanySerializer, EntitySerializer

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = '__all__'

class EmployeeSerializer(serializers.ModelSerializer):
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all())#PositionSerializer()
    accrued_vacation_days = serializers.ReadOnlyField()

    class Meta:
        model = Employee
        fields = '__all__'
    
    def to_representation(self, instance):
        # optionally embed the Position details
        rep = super().to_representation(instance)
        rep['position'] = PositionSerializer(instance.position).data if instance.position else None
        return rep
    
    def validate(self, data):
        position = data.get('position')
        salary = data.get('salary')
        if position:
            if isinstance(position, int):
                position = Position.objects.get(id=position['id'])
            if position.min_salary and salary < position.min_salary:
                raise serializers.ValidationError(f"Salary must be at least {position.min_salary} for this position.")
            if position.max_salary and salary > position.max_salary:
                raise serializers.ValidationError(f"Salary cannot exceed {position.max_salary} for this position.")
        return data
    
    def update(self, instance, validated_data):
        position_data = validated_data.pop('position', None)
        if isinstance(position_data, int):
            position_id = position_data.get('id')
            if position_id:
                validated_data['position'] = Position.objects.get(id=position_id)
        return super().update(instance, validated_data)
    
class TimeTrackingSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())

    class Meta:
        model = TimeTracking
        fields = '__all__'

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Optionally embed employee
        rep['employee'] = EmployeeSerializer(instance.employee).data
        return rep
    

class KPISerializer(serializers.ModelSerializer):
    employee = EmployeeSerializer()
    
    class Meta:
        model = KPI
        fields = '__all__'

class BonusSerializer(serializers.ModelSerializer):
    employee = EmployeeSerializer()
    
    class Meta:
        model = Bonus
        fields = '__all__'

class PayrollSerializer(serializers.ModelSerializer):
    """
    Basic serializer for the payroll data.
    """
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())

    class Meta:
        model = Payroll
        fields = '__all__'

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # embed employee details
        rep['employee'] = EmployeeSerializer(instance.employee).data
        return rep
    


class PayrollRecalculationSerializer(serializers.Serializer):
    payroll_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="List of Payroll IDs to recalculate"
    )


class PayrollGenerationSerializer(serializers.Serializer):
    company_id = serializers.IntegerField()
    employee_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Optionally specify which employees."
    )
    pay_date = serializers.DateField(required=False)
    simulate = serializers.BooleanField(
        default=False,
        help_text="If true, do not commit DB changes."
    )

class RecurringAdjustmentSerializer(serializers.ModelSerializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())

    class Meta:
        model = RecurringAdjustment
        fields = '__all__'

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['employee'] = EmployeeSerializer(instance.employee).data
        return rep
    

    def validate(self, data):
        print("Incoming data from frontend:", data)
        return data

    def update(self, instance, validated_data):
        print("Validated data for update:", validated_data)
        return super().update(instance, validated_data)

class PayrollBulkStatusSerializer(serializers.Serializer):
    """
    For the bulk status update action.
    """
    payroll_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        help_text="List of Payroll IDs to update."
    )
    new_status = serializers.ChoiceField(
        choices=Payroll.STATUS_CHOICES,
        help_text="One of pending, approved, or paid."
    )
    simulate = serializers.BooleanField(
        default=False,
        help_text="If true, we do not commit changes."
    )