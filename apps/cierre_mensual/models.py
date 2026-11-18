from django.db import models
from django.db.models import Q


class CierreMensual(models.Model):
    ORIGENES = [
        ('manual', 'Manual'),
        ('automatico', 'Automático'),
    ]

    inicio_periodo = models.DateTimeField()
    cerrado_en = models.DateTimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    origen = models.CharField(
        max_length=12,
        choices=ORIGENES,
        blank=True,
    )
    archivo_excel = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'CierreMensual'
        ordering = ('-inicio_periodo', '-pk')
        verbose_name = 'cierre mensual'
        verbose_name_plural = 'cierres mensuales'
        constraints = [
            models.UniqueConstraint(
                fields=('activo',),
                condition=Q(activo=True),
                name='uq_cierre_mensual_activo',
            ),
        ]

    def __str__(self):
        return f'Periodo iniciado {self.inicio_periodo:%d/%m/%Y %H:%M}'
