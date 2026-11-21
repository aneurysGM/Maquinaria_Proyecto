from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class PuntoChecklist(models.Model):
    PUNTOS = (
        ('fluidos', 'Niveles de fluidos'),
        ('hidraulico', 'Sistema hidráulico'),
        ('rodaje', 'Orugas o neumáticos'),
        ('electrico', 'Componentes eléctricos'),
    )
    RESULTADOS = (
        ('correcto', 'Correcto'),
        ('atencion', 'Requiere atención'),
        ('no_aplica', 'No aplica'),
    )

    mantenimiento = models.ForeignKey(
        'mantenimiento.Mantenimiento',
        on_delete=models.PROTECT,
        related_name='puntos_checklist',
    )
    punto = models.CharField(max_length=16, choices=PUNTOS)
    resultado = models.CharField(max_length=12, choices=RESULTADOS)
    observacion = models.CharField(max_length=500, blank=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='puntos_checklist_revisados',
    )
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('punto',)
        constraints = [
            models.UniqueConstraint(
                fields=('mantenimiento', 'punto'),
                name='uq_checklist_mantenimiento_punto',
            ),
        ]


class BorradorOrden(models.Model):
    mantenimiento = models.OneToOneField(
        'mantenimiento.Mantenimiento',
        on_delete=models.CASCADE,
        related_name='borrador',
    )
    datos = models.JSONField(default=dict)
    actualizado_en = models.DateTimeField(auto_now=True)


class RegistroTrabajo(models.Model):
    mantenimiento = models.ForeignKey(
        'mantenimiento.Mantenimiento',
        on_delete=models.PROTECT,
        related_name='registros_trabajo',
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='registros_ordenes_trabajo',
    )
    estado = models.CharField(
        max_length=24,
        choices=(
            ('pendiente', 'Pendiente'),
            ('diagnostico', 'En diagnóstico'),
            ('reparacion', 'En reparación'),
            ('esperando_repuestos', 'Esperando repuestos'),
            ('finalizada', 'Finalizada'),
        ),
    )
    horas = models.DecimalField(
        max_digits=8,
        decimal_places=1,
        validators=(MinValueValidator(0),),
    )
    observaciones = models.TextField(max_length=2000)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-creado_en', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(horas__gte=0),
                name='CK_RegistroTrabajo_Horas_NoNegativas',
            ),
        ]


class ComentarioOrden(models.Model):
    mantenimiento = models.ForeignKey(
        'mantenimiento.Mantenimiento',
        on_delete=models.CASCADE,
        related_name='comentarios_tecnicos',
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comentarios_ordenes',
    )
    comentario = models.TextField(max_length=2000)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-creado_en', '-pk')


class Repuesto(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120)
    unidad_medida = models.CharField(max_length=20, default='pieza')
    existencia = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=(MinValueValidator(0),),
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ('codigo',)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(existencia__gte=0),
                name='CK_Repuesto_Existencia_NoNegativa',
            ),
        ]

    def __str__(self):
        return f'{self.codigo} · {self.nombre}'


class SolicitudRepuesto(models.Model):
    ESTADOS = (
        ('pendiente', 'Pendiente'),
        ('aprobada', 'Aprobada'),
        ('recibida', 'Recibida'),
        ('rechazada', 'Rechazada'),
    )

    mantenimiento = models.ForeignKey(
        'mantenimiento.Mantenimiento',
        on_delete=models.PROTECT,
        related_name='solicitudes_repuestos',
    )
    solicitada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='solicitudes_repuestos_creadas',
    )
    estado = models.CharField(max_length=12, choices=ESTADOS, default='pendiente')
    creada_en = models.DateTimeField(auto_now_add=True)
    resuelta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitudes_repuestos_resueltas',
    )
    resuelta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-creada_en', '-pk')


class DetalleSolicitudRepuesto(models.Model):
    solicitud = models.ForeignKey(
        SolicitudRepuesto,
        on_delete=models.PROTECT,
        related_name='detalles',
    )
    codigo = models.CharField(max_length=40)
    nombre = models.CharField(max_length=120)
    unidad_medida = models.CharField(max_length=20, default='pieza')
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
    )
    repuesto = models.ForeignKey(
        Repuesto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='solicitudes_recibidas',
    )

    class Meta:
        ordering = ('pk',)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='CK_DetalleSolicitudRepuesto_Cantidad_Positiva',
            ),
        ]


class ConsumoRepuesto(models.Model):
    mantenimiento = models.ForeignKey(
        'mantenimiento.Mantenimiento',
        on_delete=models.PROTECT,
        related_name='consumos_repuestos',
    )
    repuesto = models.ForeignKey(
        Repuesto,
        on_delete=models.PROTECT,
        related_name='consumos',
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='consumos_repuestos_registrados',
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-creado_en', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='CK_ConsumoRepuesto_Cantidad_Positiva',
            ),
        ]


class EntradaRepuesto(models.Model):
    repuesto = models.ForeignKey(
        Repuesto,
        on_delete=models.PROTECT,
        related_name='entradas',
    )
    solicitud = models.ForeignKey(
        SolicitudRepuesto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='entradas_registradas',
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='entradas_repuestos_registradas',
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-creado_en', '-pk')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='CK_EntradaRepuesto_Cantidad_Positiva',
            ),
        ]
