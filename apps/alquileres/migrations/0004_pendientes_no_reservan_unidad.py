from django.db import migrations


def liberar_unidades_solo_pendientes(apps, schema_editor):
    SolicitudAlquiler = apps.get_model('alquileres', 'SolicitudAlquiler')
    Unidad = apps.get_model('inventario', 'Unidad')
    alias = schema_editor.connection.alias

    unidades_pendientes = SolicitudAlquiler.objects.using(alias).filter(
        estado='Pendiente',
    ).values('unidad_id')
    unidades_aprobadas = SolicitudAlquiler.objects.using(alias).filter(
        estado='Aprobada',
        fecha_retorno__isnull=True,
    ).values('unidad_id')
    Unidad.objects.using(alias).filter(
        pk__in=unidades_pendientes,
        activo=True,
        maquinaria__activo=True,
        estado='Alquilado',
    ).exclude(
        pk__in=unidades_aprobadas,
    ).update(estado='Disponible')


class Migration(migrations.Migration):

    dependencies = [
        ('alquileres', '0003_estado_solicitud_vencida'),
        ('inventario', '0003_alter_maquinaria_descripcion_alter_maquinaria_nombre'),
    ]

    operations = [
        migrations.RunPython(
            liberar_unidades_solo_pendientes,
            migrations.RunPython.noop,
        ),
    ]
