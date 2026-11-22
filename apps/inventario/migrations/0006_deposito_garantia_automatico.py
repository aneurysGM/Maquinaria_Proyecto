from decimal import Decimal, ROUND_HALF_UP

from django.core.validators import MinValueValidator
from django.db import migrations, models


def recalcular_depositos(apps, schema_editor):
    Maquinaria = apps.get_model('inventario', 'Maquinaria')
    for maquinaria in Maquinaria.objects.all().iterator():
        maquinaria.deposito_garantia = (
            maquinaria.costo_adquisicion * Decimal('0.08')
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        maquinaria.save(update_fields=['deposito_garantia'])


class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0005_unidad_intervalo_mantenimiento_horas_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='maquinaria',
            name='deposito_garantia',
            field=models.DecimalField(
                db_column='DepositoGarantia',
                decimal_places=2,
                default=0,
                editable=False,
                max_digits=18,
                validators=[MinValueValidator(0)],
                verbose_name='Depósito de garantía base (RD$)',
            ),
        ),
        migrations.RunPython(recalcular_depositos, migrations.RunPython.noop),
    ]
