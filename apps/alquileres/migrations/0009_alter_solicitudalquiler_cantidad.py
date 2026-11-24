import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alquileres', '0008_merge_20261121'),
    ]

    operations = [
        migrations.AlterField(
            model_name='solicitudalquiler',
            name='cantidad',
            field=models.PositiveIntegerField(blank=True, default=0, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Cantidad de planes'),
        ),
    ]
