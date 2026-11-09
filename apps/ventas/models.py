from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class PresupuestoAlquiler(models.Model):
    solicitud = models.OneToOneField(
        'alquileres.SolicitudAlquiler',
        on_delete=models.PROTECT,
        related_name='presupuesto',
    )
    tarifa_periodo = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(0)]
    )
    importe_renta = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(0)]
    )
    deposito_garantia = models.DecimalField(
        max_digits=18, decimal_places=2, validators=[MinValueValidator(0)]
    )
    mora_total = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(0)],
    )
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    mora_actualizada_en = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = 'PresupuestoAlquiler'
        ordering = ('-creado_en', '-id')
        verbose_name = 'presupuesto de alquiler'
        verbose_name_plural = 'presupuestos de alquiler'

    @property
    def importe_total(self):
        return self.importe_renta + self.deposito_garantia + self.mora_total

    @property
    def mora_aplicable(self):
        solicitud = self.solicitud
        if solicitud.fecha_retorno or not solicitud.politica_mora_aplica:
            return self.mora_total
        return self.calcular_mora(solicitud.dias_atraso_actual)

    @property
    def importe_total_actual(self):
        return self.importe_renta + self.deposito_garantia + self.mora_aplicable

    @property
    def total_pagado(self):
        return self.pagos.aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def saldo_pendiente(self):
        return max(
            self.importe_total - self.total_pagado - self.deposito_reembolsado,
            Decimal('0.00'),
        )

    @property
    def saldo_pendiente_actual(self):
        return max(
            self.importe_total_actual
            - self.total_pagado
            - self.deposito_reembolsado,
            Decimal('0.00'),
        )

    @property
    def deposito_reembolsado(self):
        return self.reembolsos_deposito.aggregate(
            total=Sum('monto')
        )['total'] or Decimal('0.00')

    @property
    def deposito_pagado(self):
        return self.pagos.filter(
            concepto='deposito'
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    @property
    def deposito_por_reembolsar(self):
        return max(
            self.deposito_pagado - self.deposito_reembolsado,
            Decimal('0.00'),
        )

    @property
    def tarifa_diaria_equivalente(self):
        if self.solicitud.plan == 'semanal':
            return self.tarifa_periodo / Decimal('7')
        if self.solicitud.plan == 'mensual':
            return self.tarifa_periodo / Decimal('30')
        return self.tarifa_periodo

    def calcular_mora(self, dias_atraso):
        primeros_dias = min(max(dias_atraso, 0), 3)
        dias_adicionales = max(dias_atraso - 3, 0)
        factor = Decimal(primeros_dias) * Decimal('0.10')
        factor += Decimal(dias_adicionales) * Decimal('0.20')
        return (self.tarifa_diaria_equivalente * factor).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def __str__(self):
        return f'Presupuesto #{self.pk} - Solicitud #{self.solicitud_id}'


class PagoAlquiler(models.Model):
    CONCEPTOS = [
        ('renta', 'Renta'),
        ('deposito', 'Depósito de garantía'),
        ('mora', 'Mora'),
    ]
    METODOS = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    ]

    presupuesto = models.ForeignKey(
        PresupuestoAlquiler,
        on_delete=models.PROTECT,
        related_name='pagos',
    )
    concepto = models.CharField(
        max_length=12, choices=CONCEPTOS, default='renta'
    )
    monto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    metodo = models.CharField(max_length=20, choices=METODOS)
    referencia = models.CharField(max_length=120, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='pagos_alquiler_registrados',
    )
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = 'PagoAlquiler'
        ordering = ('-creado_en', '-id')
        verbose_name = 'pago de alquiler'
        verbose_name_plural = 'pagos de alquiler'

    def clean(self):
        super().clean()
        if not self.presupuesto_id or self.monto is None:
            return
        presupuesto = self.presupuesto
        if self.concepto == 'renta':
            limite = presupuesto.importe_renta
        elif self.concepto == 'deposito':
            limite = presupuesto.deposito_garantia
        else:
            limite = presupuesto.mora_aplicable
        pagos_existentes = presupuesto.pagos.filter(
            concepto=self.concepto
        ).exclude(pk=self.pk).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        if pagos_existentes + self.monto > limite:
            raise ValidationError({
                'monto': 'El pago supera el saldo pendiente de ese concepto.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Pago de {self.monto} para el presupuesto #{self.presupuesto_id}'


class ReembolsoDeposito(models.Model):
    METODOS = PagoAlquiler.METODOS

    presupuesto = models.ForeignKey(
        PresupuestoAlquiler,
        on_delete=models.PROTECT,
        related_name='reembolsos_deposito',
    )
    monto = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    metodo = models.CharField(max_length=20, choices=METODOS)
    referencia = models.CharField(max_length=120, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reembolsos_deposito_registrados',
    )
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = 'ReembolsoDeposito'
        ordering = ('-creado_en', '-id')
        verbose_name = 'reembolso de depósito'
        verbose_name_plural = 'reembolsos de depósitos'

    def clean(self):
        super().clean()
        if not self.presupuesto_id or self.monto is None:
            return
        presupuesto = self.presupuesto
        if not presupuesto.solicitud.fecha_retorno:
            raise ValidationError(
                'El depósito solo se puede reembolsar después de registrar el retorno.'
            )
        pagos_deposito = presupuesto.pagos.filter(
            concepto='deposito'
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        reembolsos_previos = presupuesto.reembolsos_deposito.exclude(
            pk=self.pk
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')
        if reembolsos_previos + self.monto > pagos_deposito:
            raise ValidationError({
                'monto': 'El reembolso no puede superar el depósito recibido y aún no devuelto.'
            })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Reembolso de {self.monto} para el presupuesto #{self.presupuesto_id}'
