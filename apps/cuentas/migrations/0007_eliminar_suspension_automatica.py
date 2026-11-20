from django.db import migrations, models


def reactivar_cuentas_suspendidas(apps, schema_editor):
    UsuarioPersonalizado = apps.get_model('cuentas', 'UsuarioPersonalizado')
    UsuarioPersonalizado.objects.filter(
        suspension_hasta__isnull=False,
    ).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('cuentas', '0006_solicitud_cambio_correo'),
    ]

    operations = [
        migrations.RunPython(
            reactivar_cuentas_suspendidas,
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(
            model_name='usuariopersonalizado',
            name='suspension_hasta',
        ),
        migrations.AddField(
            model_name='usuariopersonalizado',
            name='motivo_inactivacion',
            field=models.TextField(
                blank=True,
                db_column='MotivoInactivacion',
                verbose_name='Motivo de inactivación',
            ),
        ),
    ]
