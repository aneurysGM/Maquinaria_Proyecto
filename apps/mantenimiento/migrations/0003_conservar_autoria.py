from django.db import migrations
from django.db.models import F


def conservar_autoria(apps, schema_editor):
    Mantenimiento = apps.get_model('mantenimiento', 'Mantenimiento')
    # Antes de separar ambos campos, tecnico identificaba al usuario de la sesión.
    Mantenimiento.objects.using(schema_editor.connection.alias).filter(
        registrado_por__isnull=True,
    ).update(registrado_por_id=F('tecnico_id'))


class Migration(migrations.Migration):
    dependencies = [('mantenimiento', '0002_mantenimiento_registrado_por')]
    operations = [migrations.RunPython(conservar_autoria, migrations.RunPython.noop)]
