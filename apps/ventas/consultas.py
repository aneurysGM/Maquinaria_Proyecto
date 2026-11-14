from datetime import timedelta

from django.utils import timezone

from apps.alquileres.models import SolicitudAlquiler
from .models import PresupuestoAlquiler


def presupuestos_con_pago_vencido(*, ahora=None):
    """Solo existe vencimiento del pago inicial; no se inventa uno para la mora."""
    ahora = ahora or timezone.now()
    limite = ahora - timedelta(days=SolicitudAlquiler.PLAZO_PAGO_DIAS)
    candidatos = PresupuestoAlquiler.objects.filter(
        solicitud__estado__in=('Aprobada', 'Vencida'),
        solicitud__fecha_salida__isnull=True,
        solicitud__fecha_revision__lte=limite,
    ).select_related('solicitud__cliente', 'solicitud__unidad__maquinaria').prefetch_related(
        'pagos',
    ).order_by('solicitud__fecha_revision', 'pk')
    return [p for p in candidatos if not p.solicitud.pago_inicial_completo and p.saldo_pendiente_actual > 0]
