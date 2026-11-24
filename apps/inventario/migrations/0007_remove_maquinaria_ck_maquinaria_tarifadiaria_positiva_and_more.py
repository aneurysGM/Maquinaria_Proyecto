from decimal import Decimal, ROUND_HALF_UP

import django.core.validators
from django.conf import settings
from django.db import migrations, models


def redondear_numericos(apps, schema_editor):
    Maquinaria = apps.get_model('inventario', 'Maquinaria')
    Unidad = apps.get_model('inventario', 'Unidad')

    for maquinaria in Maquinaria.objects.all().iterator():
        for campo in (
            'costo_adquisicion',
            'tarifa_diaria',
            'tarifa_semanal',
            'tarifa_mensual',
            'deposito_garantia',
        ):
            valor = Decimal(str(getattr(maquinaria, campo) or 0))
            setattr(maquinaria, campo, int(valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
        maquinaria.save(update_fields=[
            'costo_adquisicion', 'tarifa_diaria', 'tarifa_semanal',
            'tarifa_mensual', 'deposito_garantia',
        ])

    for unidad in Unidad.objects.all().iterator():
        campos = ['horas_uso']
        unidad.horas_uso = int(
            Decimal(str(unidad.horas_uso or 0)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        )
        for campo in ('intervalo_mantenimiento_horas', 'proximo_mantenimiento_horas'):
            valor = getattr(unidad, campo)
            if valor is not None:
                setattr(
                    unidad,
                    campo,
                    int(Decimal(str(valor)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
                )
                campos.append(campo)
        unidad.save(update_fields=campos)


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0006_deposito_garantia_automatico'),
        ('marca', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(redondear_numericos, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='maquinaria',
            name='CK_Maquinaria_TarifaDiaria_Positiva',
        ),
        migrations.RemoveConstraint(
            model_name='maquinaria',
            name='CK_Maquinaria_TarifaSemanal_Positiva',
        ),
        migrations.RemoveConstraint(
            model_name='maquinaria',
            name='CK_Maquinaria_TarifaMensual_Positiva',
        ),
        migrations.AlterField(
            model_name='maquinaria',
            name='costo_adquisicion',
            field=models.PositiveBigIntegerField(blank=True, db_column='CostoAdquisicion', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Costo de adquisición'),
        ),
        migrations.AlterField(
            model_name='maquinaria',
            name='deposito_garantia',
            field=models.PositiveBigIntegerField(blank=True, db_column='DepositoGarantia', default=0, editable=False, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Depósito de garantía base (RD$)'),
        ),
        migrations.AlterField(
            model_name='maquinaria',
            name='tarifa_diaria',
            field=models.PositiveBigIntegerField(blank=True, db_column='TarifaDiaria', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Tarifa diaria ($)'),
        ),
        migrations.AlterField(
            model_name='maquinaria',
            name='tarifa_mensual',
            field=models.PositiveBigIntegerField(blank=True, db_column='TarifaMensual', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Tarifa mensual ($)'),
        ),
        migrations.AlterField(
            model_name='maquinaria',
            name='tarifa_semanal',
            field=models.PositiveBigIntegerField(blank=True, db_column='TarifaSemanal', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Tarifa semanal ($)'),
        ),
        migrations.AlterField(
            model_name='unidad',
            name='horas_uso',
            field=models.PositiveBigIntegerField(blank=True, db_column='HorasUso', default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Horas de uso'),
        ),
        migrations.AlterField(
            model_name='unidad',
            name='intervalo_mantenimiento_horas',
            field=models.PositiveBigIntegerField(blank=True, db_column='IntervaloMantenimientoHoras', null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name='Intervalo de mantenimiento (horas)'),
        ),
        migrations.AlterField(
            model_name='unidad',
            name='proximo_mantenimiento_horas',
            field=models.PositiveBigIntegerField(blank=True, db_column='ProximoMantenimientoHoras', null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Próximo mantenimiento (horómetro)'),
        ),
        migrations.AddConstraint(
            model_name='maquinaria',
            constraint=models.CheckConstraint(condition=models.Q(('tarifa_diaria__gte', 0)), name='CK_Maquinaria_TarifaDiaria_Positiva'),
        ),
        migrations.AddConstraint(
            model_name='maquinaria',
            constraint=models.CheckConstraint(condition=models.Q(('tarifa_semanal__gte', 0)), name='CK_Maquinaria_TarifaSemanal_Positiva'),
        ),
        migrations.AddConstraint(
            model_name='maquinaria',
            constraint=models.CheckConstraint(condition=models.Q(('tarifa_mensual__gte', 0)), name='CK_Maquinaria_TarifaMensual_Positiva'),
        ),
    ]
