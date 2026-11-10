from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.ventas.models import PresupuestoAlquiler
from .bloqueos import bloquear_unidad
from .models import SolicitudAlquiler


def pago_inicial_completo(solicitud):
    try:
        presupuesto = solicitud.presupuesto
    except PresupuestoAlquiler.DoesNotExist:
        return False

    pagos = presupuesto.pagos.aggregate(
        renta=Sum('monto', filter=Q(concepto='renta')),
        deposito=Sum('monto', filter=Q(concepto='deposito')),
    )
    return (
        (pagos['renta'] or Decimal('0.00')) >= presupuesto.importe_renta
        and (pagos['deposito'] or Decimal('0.00')) >= presupuesto.deposito_garantia
    )


def puede_aprobar_reserva(solicitud, unidad):
    if not unidad.activo or not unidad.maquinaria.activo:
        return False
    if unidad.estado == 'Disponible':
        return True
    if unidad.estado != 'Alquilado' or solicitud.fecha_salida is not None:
        return False

    otras_pendientes = SolicitudAlquiler.objects.filter(
        unidad=unidad,
        estado='Pendiente',
    ).exclude(pk=solicitud.pk).exists()
    otras_aprobadas = SolicitudAlquiler.objects.filter(
        unidad=unidad,
        estado='Aprobada',
        fecha_retorno__isnull=True,
    ).exclude(pk=solicitud.pk).exists()
    return not (otras_pendientes or otras_aprobadas)


def liberar_unidad_si_no_reservada(unidad, solicitud_id):
    if unidad.estado != 'Alquilado':
        return False

    otra_reserva = SolicitudAlquiler.objects.filter(
        unidad=unidad,
    ).exclude(pk=solicitud_id).filter(
        Q(estado='Pendiente')
        | Q(estado='Aprobada', fecha_retorno__isnull=True)
    ).exists()
    if otra_reserva:
        return False

    unidad.estado = 'Disponible'
    unidad.save(update_fields=['estado'])
    return True


def expirar_solicitud_si_corresponde(solicitud_id, *, ahora=None):
    ahora = ahora or timezone.now()
    unidad_id = SolicitudAlquiler.objects.filter(
        pk=solicitud_id,
    ).values_list('unidad_id', flat=True).first()
    if unidad_id is None:
        return False

    with transaction.atomic():
        unidad = bloquear_unidad(pk=unidad_id)
        solicitud = SolicitudAlquiler.objects.select_for_update().filter(
            pk=solicitud_id,
        ).first()
        if solicitud is None or solicitud.unidad_id != unidad.pk:
            return False
        if (
            solicitud.estado != 'Aprobada'
            or solicitud.fecha_salida is not None
            or solicitud.fecha_limite_pago is None
            or solicitud.fecha_limite_pago > ahora
            or pago_inicial_completo(solicitud)
        ):
            return False

        solicitud.estado = 'Vencida'
        solicitud.save(update_fields=['estado'])
        liberar_unidad_si_no_reservada(unidad, solicitud.pk)
        return True


def expirar_solicitudes_vencidas(*, ahora=None):
    ahora = ahora or timezone.now()
    limite = ahora - timedelta(days=SolicitudAlquiler.PLAZO_PAGO_DIAS)
    ids = list(SolicitudAlquiler.objects.filter(
        estado='Aprobada',
        fecha_revision__isnull=False,
        fecha_revision__lte=limite,
        fecha_salida__isnull=True,
    ).order_by('fecha_revision', 'pk').values_list('pk', flat=True))
    return sum(
        expirar_solicitud_si_corresponde(solicitud_id, ahora=ahora)
        for solicitud_id in ids
    )
