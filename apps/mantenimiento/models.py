from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from apps.inventario.models import Unidad


class Mantenimiento(models.Model):
    TIPOS = (
        ('Preventivo', 'Preventivo'), 
        ('Correctivo', 'Correctivo')
    )

    id = models.AutoField(primary_key=True, db_column='MantenimientoID')
    unidad = models.ForeignKey(
        Unidad, 
        models.PROTECT, 
        db_column='UnidadID', 
        related_name='mantenimientos',
        verbose_name='Unidad física'
    )
    fecha = models.DateField(db_column='FechaInicio', verbose_name='Fecha de mantenimiento')
    fecha_fin = models.DateField(null=True, blank=True, editable=False, db_column='FechaFin')
    tipo = models.CharField(max_length=12, choices=TIPOS, db_column='Tipo', verbose_name='Tipo')
    descripcion = models.CharField(max_length=300, null=True, blank=True, db_column='Descripcion', verbose_name='Descripción')
    costo = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(0)], db_column='Costo',
        verbose_name='Costo ($)'
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, blank=True, editable=False,
        db_column='TecnicoResponsableID', related_name='mantenimientos_registrados',
    )

    class Meta:
        verbose_name = 'mantenimiento'
        verbose_name_plural = 'mantenimientos'
        db_table = 'Mantenimiento'
        ordering = ('-fecha', '-id')
        constraints = (
            models.CheckConstraint(condition=models.Q(costo__gte=0), name='CK_Mantenimiento_Costo_NoNegativo'),
            models.CheckConstraint(
                condition=models.Q(tipo__in=['Preventivo', 'Correctivo']),
                name='CK_Mantenimiento_Tipo_Valido',
            ),
        )

    def clean(self):
        super().clean()
        if self._state.adding:
            errores = {}
            if not (self.descripcion or '').strip():
                errores['descripcion'] = 'La descripción es obligatoria en registros nuevos.'
            if self.tecnico_id is None:
                errores['tecnico'] = 'El técnico responsable es obligatorio.'
            if errores:
                raise ValidationError(errores)

    def __str__(self):
        return f'{self.unidad} · {self.fecha} · {self.tipo}'