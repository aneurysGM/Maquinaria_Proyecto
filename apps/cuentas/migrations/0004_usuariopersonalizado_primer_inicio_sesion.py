from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuentas', '0003_usuariopersonalizado_especialidad'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuariopersonalizado',
            name='primer_inicio_sesion',
            field=models.BooleanField(
                db_column='PrimerInicioSesion',
                default=False,
                verbose_name='Debe cambiar la contraseña en su primer inicio de sesión',
            ),
        ),
    ]
