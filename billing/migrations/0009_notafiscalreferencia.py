# Generated manually for NotaFiscalReferencia (vínculo NF → NF referenciada)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('multitenancy', '0028_company_notes_entity_notes_etlpipelinelog_notes_and_more'),
        ('billing', '0008_nfeinutilizacao'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotaFiscalReferencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, null=True)),
                ('chave_referenciada', models.CharField(db_index=True, help_text='Chave de 44 dígitos (refNFe) da NF ao qual esta nota faz referência.', max_length=44, verbose_name='Chave NF referenciada')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(class)s_company', to='multitenancy.company')),
                ('nota_fiscal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referencias_a_outras_notas', to='billing.notafiscal', verbose_name='Nota Fiscal (que referencia)')),
                ('nota_referenciada', models.ForeignKey(blank=True, help_text='Preenchido quando já existe NotaFiscal com chave = chave_referenciada.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notas_que_me_referenciam', to='billing.notafiscal', verbose_name='Nota referenciada (quando existir)')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created_by', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated_by', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Referência entre NFs',
                'verbose_name_plural': 'Referências entre NFs',
                'ordering': ['nota_fiscal', 'chave_referenciada'],
            },
        ),
        migrations.AddConstraint(
            model_name='notafiscalreferencia',
            constraint=models.UniqueConstraint(fields=('company', 'nota_fiscal', 'chave_referenciada'), name='billing_nfref_company_nf_chave_uniq'),
        ),
        migrations.AddIndex(
            model_name='notafiscalreferencia',
            index=models.Index(fields=['chave_referenciada'], name='billing_nfr_chave_ref_idx'),
        ),
        migrations.AddIndex(
            model_name='notafiscalreferencia',
            index=models.Index(fields=['nota_referenciada'], name='billing_nfr_nota_ref_idx'),
        ),
    ]
