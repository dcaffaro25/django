# NORD/multitenancy/serializers.py

from rest_framework import serializers
from .models import CustomUser, Company, Entity, IntegrationRule, SubstitutionRule
from rest_framework.exceptions import ValidationError
from django.contrib.auth import authenticate
from accounting.models import Account, CostCenter
from django.core.exceptions import ObjectDoesNotExist
#from accounting.serializers import AccountSerializer, CostCenterSerializer
import secrets
import string
from django.conf import settings

class FlexibleRelatedField(serializers.PrimaryKeyRelatedField):
    """
    A flexible field for ForeignKey relationships:
    - On GET: Return the serialized object (via serializer_class if provided).
    - On POST/PUT/DELETE:
        - Accept an int (primary key).
        - Accept a dict where exactly ONE of the fields in unique_field is given.
    - unique_field can be a single string OR a list/tuple of possible unique fields.
    """

    def __init__(self, serializer_class=None, unique_field=None, **kwargs):
        """
        :param serializer_class: Serializer class to use when returning data.
        :param unique_field: a string or a list/tuple of possible unique fields
                            e.g. "username" or ("username", "email").
        """
        self.serializer_class = serializer_class
        self.unique_field = unique_field
        super().__init__(**kwargs)

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset
        model = self.parent.Meta.model._meta.get_field(self.source).related_model
        return model.objects.all()

    def to_representation(self, value):
        if self.serializer_class:
            # Check if the object's class name indicates a PK-only (deferred) object.
            if value.__class__.__name__ == 'PKOnlyObject':
                value = self.get_queryset().get(pk=value.pk)
            context = getattr(self.parent, 'context', {})
            serializer = self.serializer_class(value, context=context)
            return serializer.data
        return super().to_representation(value)

    def to_internal_value(self, data):
        queryset = self.get_queryset()
        if queryset is None:
            raise serializers.ValidationError("No queryset available for this field.")

        # 1) If we get an integer, treat it as the primary key
        if isinstance(data, int):
            print(data)
            print(self)
            print(super().to_internal_value(data))
            return super().to_internal_value(data)

        # 2) If data is a dict, we try to find exactly one matching field from unique_field
        if isinstance(data, dict):
            if not self.unique_field:
                raise serializers.ValidationError(
                    "A `unique_field` must be provided for object lookup."
                )

            # Convert single string to list for consistent logic
            if isinstance(self.unique_field, str):
                unique_fields = [self.unique_field]
            elif isinstance(self.unique_field, (list, tuple)):
                unique_fields = list(self.unique_field)
            else:
                raise serializers.ValidationError(
                    f"`unique_field` must be a string or list of strings, got {self.unique_field}."
                )

            # Find which of those fields are present in the dict (not None)
            present_fields = [(f, data[f]) for f in unique_fields if f in data and data[f] is not None]

            # We want exactly ONE of these fields to be present
            if len(present_fields) == 0:
                raise serializers.ValidationError(
                    "None of the unique_field(s) were provided in the data."
                )
            if len(present_fields) > 1:
                fields_str = ", ".join(f"{pf[0]}={pf[1]!r}" for pf in present_fields)
                raise serializers.ValidationError(
                    f"Multiple unique fields provided ({fields_str}). Only one allowed."
                )

            # Exactly one field is present
            field_name, lookup_value = present_fields[0]

            # Try to fetch a record by that single field
            try:
                return queryset.get(**{field_name: lookup_value})
            except ObjectDoesNotExist:
                raise serializers.ValidationError(
                    {field_name: f"No matching object found for {field_name}={lookup_value!r}."}
                )

        # 3) Otherwise, invalid input
        raise serializers.ValidationError(
            "Invalid input: expected either an integer ID or a dict with exactly one unique field."
        )
        
    def get_choices(self, cutoff=None):
        # Prevent the browsable API from trying to build a select widget by returning no choices.
        return {}

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "username", "email", "first_name", "last_name", "must_change_password", "is_active", "is_superuser", "is_staff"]

    def create(self, validated_data):
        # generate a secure random temporary password
        alphabet = string.ascii_letters + string.digits
        temp_password = settings.TEMP_PASSWORD

        user = CustomUser.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            password=temp_password,
            must_change_password = True, 
            is_active = True, 
            is_superuser = validated_data["is_superuser"],
            is_staff= validated_data["is_staff"],
        )

        # attach temp password so the view can send email
        user._temp_password = temp_password
        return user

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    
    def check_user(self, clean_data):
        user = authenticate(username=clean_data['username'], password=clean_data['password'])
        if not user:
            raise ValidationError('user not found')
            
        return user



class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    
class PasswordResetForceSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = CustomUser.objects.get(email=value)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("No user with this email found.")
        return value

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'

class CompanyMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'subdomain']

class RecursiveSerializer(serializers.Serializer):
    def to_representation(self, value):
        serializer = self.parent.parent.__class__(value, context=self.context)
        return serializer.data


class EntitySerializer2(serializers.ModelSerializer):
    children = RecursiveSerializer(many=True, read_only=True)

    class Meta:
        model = Entity
        fields = '__all__'

class EntityMiniSerializer(serializers.ModelSerializer):
    path = serializers.SerializerMethodField()
    
    class Meta:
        model = Entity
        fields = ['id', 'level', 'parent_id', 'name', 'path', 'inherit_accounts', 'inherit_cost_centers']
    
    def get_level(self, obj):
        """Calculate the level of the entity in the tree."""
        level = 0
        while obj.parent is not None:
            level += 1
            obj = obj.parent
        return level
    
    def get_path(self, obj):
        """Use the get_path method from the Entity model."""
        return obj.get_path()
    
class EntitySerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(source='parent.id', read_only=True)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Entity.objects.all(), required=False, allow_null=True
    )
    level = serializers.SerializerMethodField()
    path = serializers.SerializerMethodField()
    path_ids = serializers.SerializerMethodField()
    
    company = FlexibleRelatedField(
        serializer_class=CompanySerializer,
        unique_field='name'
    )
    
    accounts = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), many=True, required=False
    )
    cost_centers = serializers.PrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(), many=True, required=False
    )
    effective_accounts = serializers.SerializerMethodField()
    effective_cost_centers = serializers.SerializerMethodField()
    
    class Meta:
        model = Entity
        fields = ['id', 'name', 'company', 'parent', 'parent_id', 'level', 'path', 'path_ids',
                  'accounts', 'cost_centers',
                  'inherit_accounts', 'inherit_cost_centers',
            'effective_accounts', 'effective_cost_centers'
        ]

    def get_level(self, obj):
        """Calculate the level of the entity in the tree."""
        level = 0
        while obj.parent is not None:
            level += 1
            obj = obj.parent
        return level

    def get_path(self, obj):
        """Use the get_path method from the Entity model."""
        return obj.get_path()
    
    def get_path_ids(self, obj):
        """Retrieve the path IDs using the Entity's get_path method."""
        return obj.get_path_ids()
    
    def get_effective_accounts(self, obj):
        from accounting.serializers import AccountSerializer  # Local import
        accounts = obj.get_available_accounts()
        return AccountSerializer(accounts, many=True).data

    def get_effective_cost_centers(self, obj):
        from accounting.serializers import CostCenterSerializer  # Local import
        cost_centers = obj.get_available_cost_centers()
        return CostCenterSerializer(cost_centers, many=True).data
    
    
class IntegrationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationRule
        fields = '__all__'

class SubstitutionRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubstitutionRule
        fields = [
            'id', 'company', 'model_name', 'field_name',
            'match_type', 'match_value', 'substitution_value',
        ]