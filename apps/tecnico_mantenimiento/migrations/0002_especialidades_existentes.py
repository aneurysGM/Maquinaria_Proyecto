from django.db import migrations


def cargar_especialidades(apps, schema_editor):
    Especialidad = apps.get_model('tecnico_mantenimiento', 'EspecialidadTecnica')
    Usuario = apps.get_model('cuentas', 'UsuarioPersonalizado')
    alias = schema_editor.connection.alias
    nombres = ['Hidráulica', 'Electricidad', 'Mecánica']
    nombres.extend(Usuario.objects.using(alias).filter(rol='Técnico').exclude(
        especialidad='',
    ).values_list('especialidad', flat=True).distinct())
    for nombre in nombres:
        # Conserva las especialidades y los perfiles previos sin reescribirlos.
        Especialidad.objects.using(alias).get_or_create(nombre=nombre)


class Migration(migrations.Migration):
    dependencies = [
        ('tecnico_mantenimiento', '0001_initial'),
        ('cuentas', '0005_usuariopersonalizado_disponible'),
    ]
    operations = [migrations.RunPython(cargar_especialidades, migrations.RunPython.noop)]
