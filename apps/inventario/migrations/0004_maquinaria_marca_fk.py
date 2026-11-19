from django.db import migrations, models
import django.db.models.deletion


def migrar_marcas_existentes(apps, schema_editor):
    Maquinaria = apps.get_model('inventario', 'Maquinaria')
    Marca = apps.get_model('marca', 'Marca')
    base = schema_editor.connection.alias

    for maquinaria in Maquinaria.objects.using(base).exclude(
        marca__isnull=True,
    ).order_by('pk').iterator():
        nombre = (maquinaria.marca or '').strip()
        if not nombre:
            continue
        marca = Marca.objects.using(base).filter(nombre__iexact=nombre).first()
        if marca is None:
            marca = Marca.objects.using(base).create(nombre=nombre)
        maquinaria.marca_relacion_id = marca.pk
        maquinaria.save(using=base, update_fields=['marca_relacion'])


def restaurar_marcas_como_texto(apps, schema_editor):
    Maquinaria = apps.get_model('inventario', 'Maquinaria')
    base = schema_editor.connection.alias

    for maquinaria in Maquinaria.objects.using(base).select_related(
        'marca_relacion',
    ).iterator():
        marca = maquinaria.marca_relacion
        maquinaria.marca = marca.nombre if marca else None
        maquinaria.save(using=base, update_fields=['marca'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0003_alter_maquinaria_descripcion_alter_maquinaria_nombre'),
        ('marca', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='maquinaria',
            name='marca_relacion',
            field=models.ForeignKey(
                blank=True,
                db_column='MarcaID',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='maquinarias',
                to='marca.marca',
                verbose_name='Marca',
            ),
        ),
        migrations.RunPython(
            migrar_marcas_existentes,
            restaurar_marcas_como_texto,
        ),
        migrations.RemoveField(
            model_name='maquinaria',
            name='marca',
        ),
        migrations.RenameField(
            model_name='maquinaria',
            old_name='marca_relacion',
            new_name='marca',
        ),
    ]
