# Generated manually for NFeInutilizacao model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('multitenancy', '0028_company_notes_entity_notes_etlpipelinelog_notes_and_more'),
        ('billing', '0007_nfeevento'),
    ]

    operations = [
        migrations.CreateModel(
            name='NFeInutilizacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, null=True)),
                ('cuf', models.CharField(blank=True, max_length=2, verbose_name='UF')),
                ('ano', models.CharField(db_index=True, max_length=2, verbose_name='Ano (2 dígitos)')),
                ('cnpj', models.CharField(db_index=True, max_length=14, verbose_name='CNPJ')),
                ('modelo', models.SmallIntegerField(default=55, verbose_name='Modelo (55=NF-e)')),
                ('serie', models.SmallIntegerField(default=1, verbose_name='Série')),
                ('n_nf_ini', models.IntegerField(verbose_name='Número NF inicial')),
                ('n_nf_fin', models.IntegerField(verbose_name='Número NF final')),
                ('x_just', models.CharField(max_length=255, verbose_name='Justificativa')),
                ('protocolo', models.CharField(blank=True, max_length=20, verbose_name='Protocolo')),
                ('status_sefaz', models.CharField(blank=True, db_index=True, max_length=5, verbose_name='Status SEFAZ')),
                ('motivo_sefaz', models.CharField(blank=True, max_length=500, verbose_name='Motivo SEFAZ')),
                ('data_registro', models.DateTimeField(blank=True, null=True, verbose_name='Data registro SEFAZ')),
                ('xml_original', models.TextField(blank=True, verbose_name='XML original')),
                ('arquivo_origem', models.CharField(blank=True, max_length=500, verbose_name='Arquivo de origem')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_company', to='multitenancy.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created_by', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated_by', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Inutilização NFe',
                'verbose_name_plural': 'Inutilizações NFe',
                'ordering': ['-data_registro', 'ano', 'serie', 'n_nf_ini'],
            },
        ),
        migrations.AddConstraint(
            model_name='nfeinutilizacao',
            constraint=models.UniqueConstraint(fields=('company', 'ano', 'serie', 'n_nf_ini', 'n_nf_fin'), name='billing_nfeinut_company_ano_serie_ini_fin_uniq'),
        ),
    ]
