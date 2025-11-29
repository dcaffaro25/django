"""
Django management command para explorar dados do banco de dados.

Uso:
    python manage.py explore_data --model Account --company-id 4
    python manage.py explore_data --model Transaction --count
    python manage.py explore_data --model JournalEntry --sample 10
    python manage.py explore_data --query "SELECT COUNT(*) FROM accounting_account"
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.apps import apps
from django.db.models import Count, Sum, Avg
from decimal import Decimal
import json


class Command(BaseCommand):
    help = "Explora dados do banco de dados PostgreSQL"

    def add_arguments(self, parser):
        parser.add_argument(
            '--model',
            type=str,
            help='Nome do modelo Django (ex: Account, Transaction, JournalEntry)',
        )
        parser.add_argument(
            '--company-id',
            type=int,
            help='Filtrar por company_id',
        )
        parser.add_argument(
            '--count',
            action='store_true',
            help='Apenas contar registros',
        )
        parser.add_argument(
            '--sample',
            type=int,
            help='Mostrar N amostras',
        )
        parser.add_argument(
            '--query',
            type=str,
            help='Executar query SQL customizada',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Mostrar estatísticas do modelo',
        )
        parser.add_argument(
            '--fields',
            type=str,
            help='Campos específicos para mostrar (separados por vírgula)',
        )

    def handle(self, *args, **options):
        if options['query']:
            self.execute_custom_query(options['query'])
            return

        if not options['model']:
            self.stdout.write(self.style.ERROR('Você deve especificar --model ou --query'))
            return

        model_name = options['model']
        
        # Tentar encontrar o modelo
        model = None
        for app_config in apps.get_app_configs():
            try:
                model = apps.get_model(app_config.label, model_name)
                break
            except LookupError:
                continue

        if not model:
            self.stdout.write(self.style.ERROR(f'Modelo {model_name} não encontrado'))
            return

        self.stdout.write(self.style.SUCCESS(f'\n=== Explorando {model.__name__} ===\n'))

        # Construir queryset
        qs = model.objects.all()
        
        if options['company_id']:
            if hasattr(model, 'company_id'):
                qs = qs.filter(company_id=options['company_id'])
            elif hasattr(model, 'company'):
                qs = qs.filter(company_id=options['company_id'])

        # Contar
        total = qs.count()
        self.stdout.write(f'Total de registros: {total}')

        if options['count']:
            return

        # Estatísticas
        if options['stats']:
            self.show_stats(qs, model)
            return

        # Amostras
        if options['sample']:
            self.show_samples(qs, model, options['sample'], options.get('fields'))
        else:
            # Mostrar primeiros 10
            self.show_samples(qs, model, 10, options.get('fields'))

    def show_stats(self, qs, model):
        """Mostra estatísticas do modelo."""
        self.stdout.write('\n--- Estatísticas ---')
        
        # Contar por company se aplicável
        if hasattr(model, 'company_id'):
            by_company = qs.values('company_id').annotate(
                count=Count('id')
            ).order_by('-count')[:10]
            self.stdout.write('\nTop 10 por company_id:')
            for item in by_company:
                self.stdout.write(f"  Company {item['company_id']}: {item['count']} registros")

        # Campos numéricos
        numeric_fields = [
            f for f in model._meta.get_fields()
            if hasattr(f, 'get_internal_type') and f.get_internal_type() in ['DecimalField', 'IntegerField', 'FloatField']
        ]
        
        if numeric_fields:
            self.stdout.write('\nCampos numéricos:')
            for field in numeric_fields[:5]:  # Limitar a 5 campos
                try:
                    stats = qs.aggregate(
                        sum=Sum(field.name),
                        avg=Avg(field.name),
                        count=Count(field.name)
                    )
                    self.stdout.write(
                        f"  {field.name}: "
                        f"Sum={stats['sum'] or 0}, "
                        f"Avg={stats['avg'] or 0}, "
                        f"Count={stats['count']}"
                    )
                except Exception as e:
                    pass

    def show_samples(self, qs, model, n, fields=None):
        """Mostra amostras dos registros."""
        samples = qs[:n]
        
        if fields:
            field_list = [f.strip() for f in fields.split(',')]
        else:
            # Campos padrão
            field_list = ['id']
            if hasattr(model, 'name'):
                field_list.append('name')
            if hasattr(model, 'description'):
                field_list.append('description')
            if hasattr(model, 'date'):
                field_list.append('date')
            if hasattr(model, 'amount'):
                field_list.append('amount')
            if hasattr(model, 'company_id'):
                field_list.append('company_id')

        self.stdout.write(f'\n--- Primeiros {len(samples)} registros ---\n')
        
        for obj in samples:
            self.stdout.write(f"ID: {obj.id}")
            for field_name in field_list:
                if hasattr(obj, field_name):
                    value = getattr(obj, field_name)
                    if isinstance(value, Decimal):
                        value = float(value)
                    self.stdout.write(f"  {field_name}: {value}")
            self.stdout.write('')

    def execute_custom_query(self, query):
        """Executa uma query SQL customizada."""
        self.stdout.write(f'\n=== Executando Query ===\n{query}\n')
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                
                if cursor.description:
                    # Query retorna resultados
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchall()
                    
                    self.stdout.write(f'\nResultados ({len(rows)} linhas):\n')
                    self.stdout.write(' | '.join(columns))
                    self.stdout.write('-' * 80)
                    
                    for row in rows[:100]:  # Limitar a 100 linhas
                        self.stdout.write(' | '.join(str(val) for val in row))
                else:
                    # Query não retorna resultados (INSERT, UPDATE, etc.)
                    self.stdout.write(self.style.SUCCESS('Query executada com sucesso'))
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro ao executar query: {e}'))

