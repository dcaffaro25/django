"""
Migration to add new calculation method fields to FinancialStatementLineTemplate.

This migration adds:
- calculation_method: New enum replacing calculation_type
- sign_policy: Control how signs are presented
- include_descendants: Control MPTT descendant expansion
- manual_value: Value for manual_input calculation method
- scale: Display scale (K, M, B)
- decimal_places: Number of decimal places for display
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0057_reconciliation_accounting__status_6c6d41_idx_and_more'),
    ]

    operations = [
        # Add calculation_method field (nullable initially for migration)
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='calculation_method',
            field=models.CharField(
                blank=True,
                choices=[
                    ('ending_balance', 'Ending Balance'),
                    ('opening_balance', 'Opening Balance'),
                    ('net_movement', 'Net Movement'),
                    ('debit_total', 'Debit Total'),
                    ('credit_total', 'Credit Total'),
                    ('change_in_balance', 'Change in Balance'),
                    ('rollup_children', 'Rollup Children'),
                    ('formula', 'Formula'),
                    ('manual_input', 'Manual Input / Constant'),
                ],
                help_text='How to calculate the line value',
                max_length=30,
                null=True,
            ),
        ),
        
        # Add sign_policy field
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='sign_policy',
            field=models.CharField(
                choices=[
                    ('natural', 'Natural'),
                    ('invert', 'Invert'),
                    ('absolute', 'Absolute'),
                ],
                default='natural',
                help_text='How to present the sign of the calculated value',
                max_length=20,
            ),
        ),
        
        # Add include_descendants field
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='include_descendants',
            field=models.BooleanField(
                default=True,
                help_text='If True, include all MPTT descendants of selected account(s)',
            ),
        ),
        
        # Add manual_value field
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='manual_value',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Value for manual_input calculation method',
                max_digits=18,
                null=True,
            ),
        ),
        
        # Add scale field
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='scale',
            field=models.CharField(
                choices=[
                    ('none', 'None'),
                    ('K', 'Thousands'),
                    ('M', 'Millions'),
                    ('B', 'Billions'),
                ],
                default='none',
                help_text='Scale factor for display',
                max_length=10,
            ),
        ),
        
        # Add decimal_places field
        migrations.AddField(
            model_name='financialstatementlinetemplate',
            name='decimal_places',
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text='Number of decimal places for display',
            ),
        ),
    ]

