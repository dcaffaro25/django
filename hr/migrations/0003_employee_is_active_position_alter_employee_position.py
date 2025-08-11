from django.db import migrations, models

def fix_invalid_positions(apps, schema_editor):
    Position = apps.get_model('hr', 'Position')
    Employee = apps.get_model('hr', 'Employee')
    Company = apps.get_model('multitenancy', 'Company')

    # Get or create a default company
    default_company, _ = Company.objects.get_or_create(
        name='Default Company',
        defaults={
            'subdomain': 'default',
        }
    )

    # Create a default position
    default_position, _ = Position.objects.get_or_create(
        title='Default Position',
        company=default_company,
        defaults={
            'description': 'Assigned when no valid position exists',
            'department': 'General',
            'hierarchy_level': 10,
            'min_salary': 0.00,
            'max_salary': 5000.00,
        }
    )

    # Update employees with invalid position references
    employees_with_invalid_positions = Employee.objects.filter(position_id__isnull=True)
    employees_with_invalid_positions.update(position=default_position)

    # Handle employees referencing non-existent foreign keys
    Employee.objects.exclude(position__in=Position.objects.all()).update(position=default_position)


class Migration(migrations.Migration):

    dependencies = [
        ('multitenancy', '0005_alter_company_subdomain'),
        ('hr', '0002_employee_company'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='Position',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('department', models.CharField(blank=True, max_length=100, null=True)),
                ('hierarchy_level', models.PositiveIntegerField(blank=True, null=True)),
                ('min_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('max_salary', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('company', models.ForeignKey(on_delete=models.CASCADE, related_name='positions', to='multitenancy.company')),
            ],
        ),
        migrations.AlterField(
            model_name='employee',
            name='position',
            field=models.ForeignKey(null=True, on_delete=models.SET_NULL, related_name='employees', to='hr.position'),
        ),
        migrations.RunPython(fix_invalid_positions),
    ]
