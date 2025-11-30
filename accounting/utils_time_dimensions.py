"""
Time Dimension Utilities for Financial Statements

Provides utilities for grouping financial data by time dimensions
(days, weeks, months, quarters, semesters, years) and calculating comparisons.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
from calendar import monthrange
import math


TIME_DIMENSIONS = {
    'day': 'day',
    'week': 'week',
    'month': 'month',
    'quarter': 'quarter',
    'semester': 'semester',
    'year': 'year',
}


def get_period_start(date_obj: date, dimension: str) -> date:
    """
    Get the start date of the period containing the given date.
    
    Parameters
    ----------
    date_obj: date
        The date within the period
    dimension: str
        Time dimension ('day', 'week', 'month', 'quarter', 'semester', 'year')
    
    Returns
    -------
    date
        Start date of the period
    """
    if dimension == 'day':
        return date_obj
    elif dimension == 'week':
        # Monday is day 0
        days_since_monday = date_obj.weekday()
        return date_obj - timedelta(days=days_since_monday)
    elif dimension == 'month':
        return date_obj.replace(day=1)
    elif dimension == 'quarter':
        quarter_month = ((date_obj.month - 1) // 3) * 3 + 1
        return date_obj.replace(month=quarter_month, day=1)
    elif dimension == 'semester':
        semester_month = 1 if date_obj.month <= 6 else 7
        return date_obj.replace(month=semester_month, day=1)
    elif dimension == 'year':
        return date_obj.replace(month=1, day=1)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")


def get_period_end(date_obj: date, dimension: str) -> date:
    """
    Get the end date of the period containing the given date.
    
    Parameters
    ----------
    date_obj: date
        The date within the period
    dimension: str
        Time dimension ('day', 'week', 'month', 'quarter', 'semester', 'year')
    
    Returns
    -------
    date
        End date of the period
    """
    if dimension == 'day':
        return date_obj
    elif dimension == 'week':
        period_start = get_period_start(date_obj, dimension)
        return period_start + timedelta(days=6)
    elif dimension == 'month':
        last_day = monthrange(date_obj.year, date_obj.month)[1]
        return date_obj.replace(day=last_day)
    elif dimension == 'quarter':
        quarter = (date_obj.month - 1) // 3 + 1
        quarter_month = quarter * 3
        last_day = monthrange(date_obj.year, quarter_month)[1]
        return date_obj.replace(month=quarter_month, day=last_day)
    elif dimension == 'semester':
        if date_obj.month <= 6:
            return date_obj.replace(month=6, day=30)
        else:
            return date_obj.replace(month=12, day=31)
    elif dimension == 'year':
        return date_obj.replace(month=12, day=31)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")


def get_period_key(date_obj: date, dimension: str) -> str:
    """
    Get a string key representing the period for grouping.
    
    Parameters
    ----------
    date_obj: date
        The date within the period
    dimension: str
        Time dimension
    
    Returns
    -------
    str
        Period key (e.g., '2025-Q1', '2025-01', '2025-W01')
    """
    if dimension == 'day':
        return date_obj.strftime('%Y-%m-%d')
    elif dimension == 'week':
        period_start = get_period_start(date_obj, dimension)
        week_num = period_start.isocalendar()[1]
        return f"{period_start.year}-W{week_num:02d}"
    elif dimension == 'month':
        return date_obj.strftime('%Y-%m')
    elif dimension == 'quarter':
        quarter = (date_obj.month - 1) // 3 + 1
        return f"{date_obj.year}-Q{quarter}"
    elif dimension == 'semester':
        semester = 1 if date_obj.month <= 6 else 2
        return f"{date_obj.year}-S{semester}"
    elif dimension == 'year':
        return str(date_obj.year)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")


def generate_periods(start_date: date, end_date: date, dimension: str) -> List[Dict[str, Any]]:
    """
    Generate a list of periods between start_date and end_date.
    
    Parameters
    ----------
    start_date: date
        Start of the range
    end_date: date
        End of the range
    dimension: str
        Time dimension
    
    Returns
    -------
    List[Dict[str, Any]]
        List of period dictionaries with 'key', 'start_date', 'end_date', 'label'
    """
    periods = []
    current = get_period_start(start_date, dimension)
    end = get_period_end(end_date, dimension)
    
    while current <= end:
        period_end = get_period_end(current, dimension)
        if period_end > end:
            period_end = end
        
        period_key = get_period_key(current, dimension)
        label = format_period_label(current, dimension)
        
        periods.append({
            'key': period_key,
            'start_date': current,
            'end_date': period_end,
            'label': label,
        })
        
        # Move to next period
        current = get_next_period_start(current, dimension)
    
    return periods


def get_next_period_start(date_obj: date, dimension: str) -> date:
    """
    Get the start date of the next period.
    
    Parameters
    ----------
    date_obj: date
        Current date
    dimension: str
        Time dimension
    
    Returns
    -------
    date
        Start date of next period
    """
    if dimension == 'day':
        return date_obj + timedelta(days=1)
    elif dimension == 'week':
        return date_obj + timedelta(days=7)
    elif dimension == 'month':
        if date_obj.month == 12:
            return date_obj.replace(year=date_obj.year + 1, month=1, day=1)
        else:
            return date_obj.replace(month=date_obj.month + 1, day=1)
    elif dimension == 'quarter':
        quarter = (date_obj.month - 1) // 3 + 1
        if quarter == 4:
            return date_obj.replace(year=date_obj.year + 1, month=1, day=1)
        else:
            return date_obj.replace(month=quarter * 3 + 1, day=1)
    elif dimension == 'semester':
        if date_obj.month <= 6:
            return date_obj.replace(month=7, day=1)
        else:
            return date_obj.replace(year=date_obj.year + 1, month=1, day=1)
    elif dimension == 'year':
        return date_obj.replace(year=date_obj.year + 1, month=1, day=1)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")


def format_period_label(date_obj: date, dimension: str) -> str:
    """
    Format a human-readable label for a period.
    
    Parameters
    ----------
    date_obj: date
        Date within the period
    dimension: str
        Time dimension
    
    Returns
    -------
    str
        Formatted label (e.g., 'January 2025', 'Q1 2025')
    """
    if dimension == 'day':
        return date_obj.strftime('%B %d, %Y')
    elif dimension == 'week':
        period_start = get_period_start(date_obj, dimension)
        period_end = get_period_end(date_obj, dimension)
        if period_start.year == period_end.year:
            return f"Week of {period_start.strftime('%b %d')} - {period_end.strftime('%b %d, %Y')}"
        else:
            return f"Week of {period_start.strftime('%b %d, %Y')} - {period_end.strftime('%b %d, %Y')}"
    elif dimension == 'month':
        return date_obj.strftime('%B %Y')
    elif dimension == 'quarter':
        quarter = (date_obj.month - 1) // 3 + 1
        return f"Q{quarter} {date_obj.year}"
    elif dimension == 'semester':
        semester = 1 if date_obj.month <= 6 else 2
        return f"S{semester} {date_obj.year}"
    elif dimension == 'year':
        return str(date_obj.year)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")


def get_comparison_period(current_start: date, current_end: date, comparison_type: str) -> Tuple[date, date]:
    """
    Get the comparison period dates based on comparison type.
    
    Parameters
    ----------
    current_start: date
        Start of current period
    current_end: date
        End of current period
    comparison_type: str
        Type of comparison:
        - 'previous_period': Same length, previous period
        - 'previous_year': Same period, previous year
        - 'ytd_previous_year': Year-to-date, previous year
        - 'last_12_months': Rolling 12 months ending at current_end
        - 'same_period_last_year': Exact same dates, previous year
    
    Returns
    -------
    Tuple[date, date]
        (comparison_start, comparison_end)
    """
    period_length = (current_end - current_start).days + 1
    
    if comparison_type == 'previous_period':
        # Same length, ending the day before current_start
        comparison_end = current_start - timedelta(days=1)
        comparison_start = comparison_end - timedelta(days=period_length - 1)
        return comparison_start, comparison_end
    
    elif comparison_type == 'previous_year':
        # Same period, previous year
        try:
            comparison_start = current_start.replace(year=current_start.year - 1)
            comparison_end = current_end.replace(year=current_end.year - 1)
            return comparison_start, comparison_end
        except ValueError:
            # Handle leap year edge case (Feb 29)
            comparison_start = current_start.replace(year=current_start.year - 1, day=28)
            comparison_end = current_end.replace(year=current_end.year - 1, day=28)
            return comparison_start, comparison_end
    
    elif comparison_type == 'ytd_previous_year':
        # Year-to-date, previous year
        year_start = current_start.replace(month=1, day=1)
        comparison_start = year_start.replace(year=year_start.year - 1)
        comparison_end = current_end.replace(year=current_end.year - 1)
        return comparison_start, comparison_end
    
    elif comparison_type == 'last_12_months':
        # Rolling 12 months
        comparison_end = current_end - timedelta(days=365)
        comparison_start = comparison_end - timedelta(days=period_length - 1)
        return comparison_start, comparison_end
    
    elif comparison_type == 'same_period_last_year':
        # Exact same dates, previous year
        try:
            comparison_start = current_start.replace(year=current_start.year - 1)
            comparison_end = current_end.replace(year=current_end.year - 1)
            return comparison_start, comparison_end
        except ValueError:
            # Handle leap year edge case
            comparison_start = current_start.replace(year=current_start.year - 1, day=28)
            comparison_end = current_end.replace(year=current_end.year - 1, day=28)
            return comparison_start, comparison_end
    
    else:
        raise ValueError(f"Unknown comparison_type: {comparison_type}")


def calculate_period_comparison(
    current_value: Decimal,
    comparison_value: Decimal,
    comparison_type: str
) -> Dict[str, Any]:
    """
    Calculate comparison metrics between current and comparison values.
    
    Parameters
    ----------
    current_value: Decimal
        Current period value
    comparison_value: Decimal
        Comparison period value
    comparison_type: str
        Type of comparison (for labeling)
    
    Returns
    -------
    Dict[str, Any]
        Comparison metrics:
        - absolute_change: current - comparison
        - percentage_change: ((current - comparison) / comparison) * 100
        - comparison_value: comparison value
        - current_value: current value
    """
    absolute_change = current_value - comparison_value
    
    if comparison_value == 0:
        percentage_change = Decimal('0.00') if current_value == 0 else None
    else:
        percentage_change = (absolute_change / comparison_value) * 100
    
    return {
        'current_value': float(current_value),
        'comparison_value': float(comparison_value),
        'absolute_change': float(absolute_change),
        'percentage_change': float(percentage_change) if percentage_change is not None else None,
        'comparison_type': comparison_type,
    }

