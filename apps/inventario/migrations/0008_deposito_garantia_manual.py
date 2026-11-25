from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0007_remove_maquinaria_ck_maquinaria_tarifadiaria_positiva_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='maquinaria',
            name='deposito_garantia',
            field=models.PositiveBigIntegerField(
                blank=True,
                db_column='DepositoGarantia',
                default=0,
                validators=[MinValueValidator(0)],
                verbose_name='Depósito de garantía (RD$)',
            ),
        ),
    ]
