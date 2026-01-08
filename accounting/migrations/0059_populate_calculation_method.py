"""
Data migration to populate calculation_method from legacy calculation_type.

Mapping:
- 'sum' -> 'net_movement' (for income_statement) or 'ending_balance' (for balance_sheet)
- 'difference' -> 'net_movement'
- 'balance' -> 'ending_balance'
- 'formula' -> 'formula'

For templates where report_type is 'cash_flow':
- 'sum' -> 'change_in_balance'
- 'balance' -> 'ending_balance'
- 'difference' -> 'change_in_balance'
"""

from django.db import migrations


def populate_calculation_method(apps, schema_editor):
    """
    Populate calculation_method based on calculation_type and template report_type.
    """
    FinancialStatementLineTemplate = apps.get_model('accounting', 'FinancialStatementLineTemplate')
    
    # Get all line templates that don't have calculation_method set
    line_templates = FinancialStatementLineTemplate.objects.filter(
        calculation_method__isnull=True
    ).select_related('template')
    
    for line in line_templates:
        calc_type = line.calculation_type
        report_type = line.template.report_type if line.template else None
        
        # Determine calculation_method based on calculation_type and report_type
        if calc_type == 'formula':
            line.calculation_method = 'formula'
        elif calc_type == 'balance':
            line.calculation_method = 'ending_balance'
        elif calc_type == 'sum':
            if report_type == 'balance_sheet':
                line.calculation_method = 'ending_balance'
            elif report_type == 'cash_flow':
                line.calculation_method = 'change_in_balance'
            else:
                line.calculation_method = 'net_movement'
        elif calc_type == 'difference':
            if report_type == 'cash_flow':
                line.calculation_method = 'change_in_balance'
            else:
                line.calculation_method = 'net_movement'
        else:
            # Default fallback
            line.calculation_method = 'ending_balance'
        
        line.save(update_fields=['calculation_method'])


def reverse_calculation_method(apps, schema_editor):
    """
    Reverse migration: clear calculation_method.
    """
    FinancialStatementLineTemplate = apps.get_model('accounting', 'FinancialStatementLineTemplate')
    FinancialStatementLineTemplate.objects.update(calculation_method=None)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0058_add_calculation_method_fields'),
    ]

    operations = [
        migrations.RunPython(
            populate_calculation_method,
            reverse_code=reverse_calculation_method,
        ),
    ]

