from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.db import migrations, models


def redondear_numericos(apps, schema_editor):
    PresupuestoAlquiler = apps.get_model('ventas', 'PresupuestoAlquiler')
    modelos_monto = (
        apps.get_model('ventas', 'PagoAlquiler'),
        apps.get_model('ventas', 'ReembolsoDeposito'),
        apps.get_model('ventas', 'ReembolsoRenta'),
    )

    for presupuesto in PresupuestoAlquiler.objects.all().iterator():
        for campo in ('tarifa_periodo', 'importe_renta', 'deposito_garantia', 'mora_total'):
            valor = Decimal(str(getattr(presupuesto, campo) or 0))
            setattr(presupuesto, campo, int(valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
        presupuesto.save(update_fields=[
            'tarifa_periodo', 'importe_renta', 'deposito_garantia', 'mora_total',
        ])

    for modelo in modelos_monto:
        for registro in modelo.objects.all().iterator():
            valor = Decimal(str(registro.monto or 0))
            registro.monto = int(valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            registro.save(update_fields=['monto'])


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0003_reembolsorenta'),
    ]

    operations = [
        migrations.RunPython(redondear_numericos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='pagoalquiler',
            name='monto',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='presupuestoalquiler',
            name='deposito_garantia',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='presupuestoalquiler',
            name='importe_renta',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='presupuestoalquiler',
            name='mora_total',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='presupuestoalquiler',
            name='tarifa_periodo',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='reembolsodeposito',
            name='monto',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='reembolsorenta',
            name='monto',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
    ]
