from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.db import migrations, models


def redondear_costos(apps, schema_editor):
    Mantenimiento = apps.get_model('mantenimiento', 'Mantenimiento')
    for mantenimiento in Mantenimiento.objects.all().iterator():
        valor = Decimal(str(mantenimiento.costo or 0))
        mantenimiento.costo = int(valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        mantenimiento.save(update_fields=['costo'])


class Migration(migrations.Migration):

    dependencies = [
        ('mantenimiento', '0005_mantenimiento_fecha_estimada_fin'),
    ]

    operations = [
        migrations.RunPython(redondear_costos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='mantenimiento',
            name='costo',
            field=models.PositiveBigIntegerField(blank=True, db_column='Costo', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Costo ($)'),
        ),
    ]
