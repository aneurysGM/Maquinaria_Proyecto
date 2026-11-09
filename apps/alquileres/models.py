from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from apps.inventario.models import Unidad


class SolicitudAlquiler(models.Model):
    PLANES = [
        ('diario', 'Diario'),
        ('semanal', 'Semanal'),
        ('mensual', 'Mensual'),
    ]
    ESTADOS = [
        ('Pendiente', 'Pendiente'), 
        ('Aprobada', 'Aprobada'), 
        ('Rechazada', 'Rechazada')
    ]
    
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        models.PROTECT, 
        related_name='solicitudes_alquiler',
        verbose_name='Cliente'
    )
    unidad = models.ForeignKey(
        Unidad, 
        models.PROTECT, 
        related_name='solicitudes_alquiler',
        verbose_name='Unidad física'
    )
    fecha_inicio = models.DateField(verbose_name='Fecha de inicio')
    fecha_fin = models.DateField(verbose_name='Fecha de fin')
    plan = models.CharField(
        max_length=10, choices=PLANES, default='diario', verbose_name='Plan de alquiler'
    )
    cantidad = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Cantidad de planes',
    )
    comentario = models.CharField(max_length=500, blank=True, verbose_name='Comentario / Obra')
    politica_mora_aplica = models.BooleanField(default=True, editable=False)
    dias_atraso = models.PositiveIntegerField(null=True, blank=True, editable=False)
    observaciones_retorno = models.CharField(max_length=1000, blank=True, editable=False)
    
    estado = models.CharField(max_length=10, choices=ESTADOS, default='Pendiente', editable=False)
    fecha_creacion = models.DateTimeField(default=timezone.now, editable=False)
    
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, blank=True, 
        related_name='solicitudes_revisadas', editable=False
    )
    fecha_revision = models.DateTimeField(null=True, blank=True, editable=False)
    
    # Datos logísticos de entrega y retorno
    fecha_salida = models.DateTimeField(null=True, blank=True, editable=False)
    entregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, blank=True, editable=False,
        related_name='salidas_registradas',
    )
    fecha_retorno = models.DateTimeField(null=True, blank=True, editable=False)
    recibido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, models.PROTECT, null=True, blank=True, editable=False,
        related_name='retornos_registrados',
    )

    @property
    def estado_entrega(self):
        if self.fecha_retorno is not None:
            return 'Devuelta'
        return 'Pendiente de devolución' if self.fecha_salida is not None else 'Sin entregar'

    @property
    def dias_atraso_actual(self):
        if not self.fecha_salida:
            return 0
        if self.fecha_retorno:
            return self.dias_atraso or 0
        return max((timezone.localdate() - self.fecha_fin).days, 0)

    @property
    def aviso_vencimiento(self):
        if self.fecha_salida is None or self.fecha_retorno is not None:
            return ''
        dias = (self.fecha_fin - timezone.localdate()).days
        if dias < 0:
            return 'Vencido'
        if dias == 0:
            return 'Vence hoy'
        if dias <= 3:
            return 'Próximo a vencer'
        return ''

    class Meta:
        verbose_name = 'solicitud de alquiler'
        verbose_name_plural = 'solicitudes de alquiler'
        db_table = 'SolicitudAlquiler'
        ordering = ('-fecha_creacion', '-id')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fecha_fin__gte=models.F('fecha_inicio')), 
                name='CK_Solicitud_Fechas'
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Pendiente', 'Aprobada', 'Rechazada']), 
                name='CK_Solicitud_Estado'
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fecha_salida__isnull=True, entregado_por__isnull=True)
                    | models.Q(fecha_salida__isnull=False, entregado_por__isnull=False, estado='Aprobada')
                ), 
                name='CK_Solicitud_Salida',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fecha_retorno__isnull=True, recibido_por__isnull=True)
                    | models.Q(
                        fecha_retorno__isnull=False, recibido_por__isnull=False,
                        fecha_salida__isnull=False, fecha_retorno__gte=models.F('fecha_salida'),
                    )
                ), 
                name='CK_Solicitud_Retorno',
            ),
            models.UniqueConstraint(
                fields=['unidad'],
                condition=models.Q(fecha_salida__isnull=False, fecha_retorno__isnull=True),
                name='UQ_Entrega_Unidad_Pendiente',
            ),
        ]

    def __str__(self):
        return f'Solicitud #{self.id} - {self.cliente.email} ({self.unidad})'
