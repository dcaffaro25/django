# Generated manually for NFeEvento model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('multitenancy', '0028_company_notes_entity_notes_etlpipelinelog_notes_and_more'),
        ('billing', '0006_alter_businesspartner_identifier_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='NFeEvento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, null=True)),
                ('chave_nfe', models.CharField(db_index=True, help_text='Chave do documento fiscal ao qual o evento se refere.', max_length=44, verbose_name='Chave NFe (44 dígitos)')),
                ('tipo_evento', models.PositiveIntegerField(choices=[(110110, 'Carta de Correção (CCe)'), (110111, 'Cancelamento'), (110112, 'Cancelamento por substituição'), (110140, 'EPEC - Emissão em contingência'), (210200, 'Manifestação: Confirmação da operação'), (210210, 'Manifestação: Ciência da operação'), (210220, 'Manifestação: Desconhecimento da operação'), (210240, 'Manifestação: Operação não realizada')], db_index=True, help_text='110110=CCe, 110111=Cancelamento, 210200=Confirmação, etc.', verbose_name='Tipo do evento')),
                ('n_seq_evento', models.PositiveSmallIntegerField(default=1, help_text='Número sequencial do evento para a mesma NF (nSeqEvento).', verbose_name='Sequência do evento')),
                ('data_evento', models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='Data/hora do evento')),
                ('descricao', models.TextField(blank=True, help_text='Para CCe: texto da correção (xCorrecao); para outros: xMotivo ou similar.', verbose_name='Descrição / correção')),
                ('protocolo', models.CharField(blank=True, max_length=20, verbose_name='Protocolo')),
                ('status_sefaz', models.CharField(blank=True, db_index=True, max_length=5, verbose_name='Status SEFAZ')),
                ('motivo_sefaz', models.CharField(blank=True, max_length=500, verbose_name='Motivo SEFAZ')),
                ('data_registro', models.DateTimeField(blank=True, null=True, verbose_name='Data registro SEFAZ')),
                ('xml_original', models.TextField(blank=True, verbose_name='XML original')),
                ('arquivo_origem', models.CharField(blank=True, max_length=500, verbose_name='Arquivo de origem')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_company', to='multitenancy.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created_by', to=settings.AUTH_USER_MODEL)),
                ('nota_fiscal', models.ForeignKey(blank=True, help_text='Preenchido quando a NF foi importada; senão use chave_nfe.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='eventos', to='billing.notafiscal', verbose_name='Nota Fiscal')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated_by', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Evento NFe',
                'verbose_name_plural': 'Eventos NFe',
                'ordering': ['chave_nfe', 'data_evento', 'n_seq_evento'],
            },
        ),
        migrations.AddConstraint(
            model_name='nfeevento',
            constraint=models.UniqueConstraint(fields=('company', 'chave_nfe', 'tipo_evento', 'n_seq_evento'), name='billing_nfeevento_company_chave_tipo_seq_uniq'),
        ),
        migrations.AddIndex(
            model_name='nfeevento',
            index=models.Index(fields=['tipo_evento', 'chave_nfe'], name='billing_nfe_tipo_ev_0a1b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='nfeevento',
            index=models.Index(fields=['status_sefaz'], name='billing_nfe_status__1d2e3f_idx'),
        ),
    ]
