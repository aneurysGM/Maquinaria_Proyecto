from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.conf import settings
from django.db import migrations, models


def redondear_numericos(apps, schema_editor):
    campos = {
        'RegistroTrabajo': ('horas',),
        'Repuesto': ('existencia',),
        'DetalleSolicitudRepuesto': ('cantidad',),
        'ConsumoRepuesto': ('cantidad',),
        'EntradaRepuesto': ('cantidad',),
    }
    for modelo, nombres in campos.items():
        Modelo = apps.get_model('ordenes_trabajo', modelo)
        for registro in Modelo.objects.all().iterator():
            for nombre in nombres:
                valor = Decimal(str(getattr(registro, nombre) or 0))
                setattr(
                    registro,
                    nombre,
                    int(valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
                )
            registro.save(update_fields=list(nombres))


class Migration(migrations.Migration):

    dependencies = [
        ('mantenimiento', '0006_alter_mantenimiento_costo'),
        ('ordenes_trabajo', '0003_borradororden'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(redondear_numericos, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='consumorepuesto',
            name='CK_ConsumoRepuesto_Cantidad_Positiva',
        ),
        migrations.RemoveConstraint(
            model_name='detallesolicitudrepuesto',
            name='CK_DetalleSolicitudRepuesto_Cantidad_Positiva',
        ),
        migrations.RemoveConstraint(
            model_name='entradarepuesto',
            name='CK_EntradaRepuesto_Cantidad_Positiva',
        ),
        migrations.AlterField(
            model_name='consumorepuesto',
            name='cantidad',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='detallesolicitudrepuesto',
            name='cantidad',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='entradarepuesto',
            name='cantidad',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='registrotrabajo',
            name='horas',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name='repuesto',
            name='existencia',
            field=models.PositiveBigIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddConstraint(
            model_name='consumorepuesto',
            constraint=models.CheckConstraint(condition=models.Q(('cantidad__gte', 0)), name='CK_ConsumoRepuesto_Cantidad_Positiva'),
        ),
        migrations.AddConstraint(
            model_name='detallesolicitudrepuesto',
            constraint=models.CheckConstraint(condition=models.Q(('cantidad__gte', 0)), name='CK_DetalleSolicitudRepuesto_Cantidad_Positiva'),
        ),
        migrations.AddConstraint(
            model_name='entradarepuesto',
            constraint=models.CheckConstraint(condition=models.Q(('cantidad__gte', 0)), name='CK_EntradaRepuesto_Cantidad_Positiva'),
        ),
    ]
