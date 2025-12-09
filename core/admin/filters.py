# core/admin/filters.py
"""
Enhanced admin filters for improved filtering experience.
"""
from datetime import timedelta
from django.contrib.admin import SimpleListFilter
from django.db import models
from django.utils import timezone
from django.db.models import Q


class DateRangeFilter(SimpleListFilter):
    """
    Advanced date range filter with presets and custom range support.
    Works with both DateField and DateTimeField.
    Usage: Create a subclass with field_name attribute or pass it via model_admin.
    """
    title = 'date range'
    parameter_name = 'date_range'
    field_name = None  # Override in subclass or set via model_admin
    
    def __init__(self, request, params, model, model_admin):
        # Get the field name from the filter instance or model_admin
        if not self.field_name:
            self.field_name = getattr(model_admin, 'date_range_field', None)
        
        if not self.field_name:
            # Try to auto-detect date field
            for field in model._meta.get_fields():
                if isinstance(field, (models.DateField, models.DateTimeField)):
                    # Prefer 'date' field, then 'created_at', then first date field
                    if field.name == 'date':
                        self.field_name = field.name
                        break
                    elif field.name == 'created_at' and not self.field_name:
                        self.field_name = field.name
                    elif not self.field_name:
                        self.field_name = field.name
        
        # Set title and parameter based on field name
        if self.field_name:
            self.title = f'{self.field_name.replace("_", " ").title()} Range'
            self.parameter_name = f'{self.field_name}_range'
        
        super().__init__(request, params, model, model_admin)
    
    def lookups(self, request, model_admin):
        """
        Return preset date range options.
        """
        if not self.field_name:
            return []
        
        now = timezone.now() if timezone.is_aware(timezone.now()) else timezone.now()
        today = now.date() if hasattr(now, 'date') else now
        
        # Calculate week start (Monday)
        days_since_monday = today.weekday()
        week_start = today - timedelta(days=days_since_monday)
        
        # Calculate month start
        month_start = today.replace(day=1)
        
        return (
            ('today', 'Today'),
            ('yesterday', 'Yesterday'),
            ('this_week', 'This Week'),
            ('last_week', 'Last Week'),
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
            ('last_7_days', 'Last 7 Days'),
            ('last_30_days', 'Last 30 Days'),
            ('last_90_days', 'Last 90 Days'),
            ('this_year', 'This Year'),
            ('last_year', 'Last Year'),
        )
    
    def queryset(self, request, queryset):
        """
        Apply date range filter to queryset.
        """
        if not self.field_name or not self.value():
            return queryset
        
        # Get the field
        try:
            field = queryset.model._meta.get_field(self.field_name)
        except models.FieldDoesNotExist:
            return queryset
        
        # Get current date/time
        now = timezone.now()
        if timezone.is_aware(now):
            today = now.date()
        else:
            today = now.date() if hasattr(now, 'date') else now
        
        # Calculate date ranges based on selection
        value = self.value()
        
        if value == 'today':
            start_date = today
            end_date = today
        elif value == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif value == 'this_week':
            days_since_monday = today.weekday()
            start_date = today - timedelta(days=days_since_monday)
            end_date = today
        elif value == 'last_week':
            days_since_monday = today.weekday()
            week_end = today - timedelta(days=days_since_monday + 1)
            start_date = week_end - timedelta(days=6)
            end_date = week_end
        elif value == 'this_month':
            start_date = today.replace(day=1)
            end_date = today
        elif value == 'last_month':
            # First day of last month
            if today.month == 1:
                start_date = today.replace(year=today.year - 1, month=12, day=1)
            else:
                start_date = today.replace(month=today.month - 1, day=1)
            # Last day of last month
            if today.month == 1:
                end_date = today.replace(year=today.year - 1, month=12, day=28)
            else:
                end_date = today.replace(month=today.month, day=1) - timedelta(days=1)
        elif value == 'last_7_days':
            start_date = today - timedelta(days=7)
            end_date = today
        elif value == 'last_30_days':
            start_date = today - timedelta(days=30)
            end_date = today
        elif value == 'last_90_days':
            start_date = today - timedelta(days=90)
            end_date = today
        elif value == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        elif value == 'last_year':
            start_date = today.replace(year=today.year - 1, month=1, day=1)
            end_date = today.replace(year=today.year - 1, month=12, day=31)
        else:
            return queryset
        
        # Apply filter based on field type
        if isinstance(field, models.DateTimeField):
            # For DateTimeField, include the entire day
            from datetime import datetime as dt
            start_datetime = dt.combine(start_date, dt.min.time())
            end_datetime = dt.combine(end_date, dt.max.time())
            
            # Make timezone-aware if needed
            if timezone.is_aware(now):
                start_datetime = timezone.make_aware(start_datetime)
                end_datetime = timezone.make_aware(end_datetime)
            
            return queryset.filter(**{
                f'{self.field_name}__gte': start_datetime,
                f'{self.field_name}__lte': end_datetime,
            })
        else:
            # For DateField
            return queryset.filter(**{
                f'{self.field_name}__gte': start_date,
                f'{self.field_name}__lte': end_date,
            })


class RecentlyModifiedFilter(SimpleListFilter):
    """
    Filter for recently modified records based on updated_at or created_at.
    """
    title = 'recently modified'
    parameter_name = 'recently_modified'
    
    def lookups(self, request, model_admin):
        return (
            ('last_24h', 'Last 24 Hours'),
            ('last_7d', 'Last 7 Days'),
            ('last_30d', 'Last 30 Days'),
            ('last_90d', 'Last 90 Days'),
        )
    
    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        
        now = timezone.now()
        value = self.value()
        
        # Determine which field to use (prefer updated_at, fallback to created_at)
        field_name = None
        if hasattr(queryset.model, 'updated_at'):
            field_name = 'updated_at'
        elif hasattr(queryset.model, 'created_at'):
            field_name = 'created_at'
        else:
            return queryset
        
        # Calculate time delta
        if value == 'last_24h':
            delta = timedelta(hours=24)
        elif value == 'last_7d':
            delta = timedelta(days=7)
        elif value == 'last_30d':
            delta = timedelta(days=30)
        elif value == 'last_90d':
            delta = timedelta(days=90)
        else:
            return queryset
        
        cutoff_time = now - delta
        return queryset.filter(**{f'{field_name}__gte': cutoff_time})


class EmptyFieldFilter(SimpleListFilter):
    """
    Generic filter for empty/non-empty fields.
    Works with nullable CharField, TextField, ForeignKey, etc.
    """
    title = 'field status'
    parameter_name = 'field_status'
    
    def __init__(self, request, params, model, model_admin):
        # Get field name from admin class attribute
        self.field_name = getattr(model_admin, 'empty_field_filter', None)
        if self.field_name:
            self.title = f'{self.field_name.replace("_", " ").title()} Status'
            self.parameter_name = f'{self.field_name}_status'
        super().__init__(request, params, model, model_admin)
    
    def lookups(self, request, model_admin):
        if not self.field_name:
            return []
        
        # Check if field exists
        try:
            field = model_admin.model._meta.get_field(self.field_name)
        except models.FieldDoesNotExist:
            return []
        
        return (
            ('empty', 'Empty'),
            ('not_empty', 'Not Empty'),
        )
    
    def queryset(self, request, queryset):
        if not self.field_name or not self.value():
            return queryset
        
        # Check if field exists
        try:
            field = queryset.model._meta.get_field(self.field_name)
        except models.FieldDoesNotExist:
            return queryset
        
        value = self.value()
        
        # Handle different field types
        if isinstance(field, (models.CharField, models.TextField)):
            if value == 'empty':
                return queryset.filter(Q(**{f'{self.field_name}__isnull': True}) | Q(**{f'{self.field_name}': ''}))
            elif value == 'not_empty':
                return queryset.exclude(Q(**{f'{self.field_name}__isnull': True}) | Q(**{f'{self.field_name}': ''}))
        elif isinstance(field, models.ForeignKey):
            if value == 'empty':
                return queryset.filter(**{f'{self.field_name}__isnull': True})
            elif value == 'not_empty':
                return queryset.exclude(**{f'{self.field_name}__isnull': True})
        else:
            # For other nullable fields
            if value == 'empty':
                return queryset.filter(**{f'{self.field_name}__isnull': True})
            elif value == 'not_empty':
                return queryset.exclude(**{f'{self.field_name}__isnull': True})
        
        return queryset

