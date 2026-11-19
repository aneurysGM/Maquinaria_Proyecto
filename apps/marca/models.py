from django.db import models
from django.db.models.functions import Lower


class Marca(models.Model):
    id = models.AutoField(primary_key=True, db_column='MarcaID')
    nombre = models.CharField(max_length=60, unique=True, db_column='Nombre')

    class Meta:
        db_table = 'Marca'
        verbose_name = 'marca'
        verbose_name_plural = 'marcas'
        ordering = ('nombre',)
        constraints = [
            models.UniqueConstraint(Lower('nombre'), name='uq_marca_nombre_ci'),
        ]

    def __str__(self):
        return self.nombre
