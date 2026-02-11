# Fix overflow: valor_unitario (15,10) allows max ~99,999; (18,10) allows up to 99,999,999

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_rename_billing_nfr_chave_ref_idx_billing_not_chave_r_0dc62e_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notafiscalitem',
            name='valor_unitario',
            field=models.DecimalField(
                decimal_places=10,
                help_text='(15,10) permitia até ~99.999; (18,10) evita overflow para valores maiores.',
                max_digits=18,
                verbose_name='Valor unitário',
            ),
        ),
    ]
