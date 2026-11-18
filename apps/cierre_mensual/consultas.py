from decimal import Decimal

from django.db.models import Sum

from apps.ventas.models import PagoAlquiler
from .models import CierreMensual


def periodo_activo():
    return CierreMensual.objects.get(activo=True)


def pagos_de_ingresos(inicio, fin=None):
    pagos = PagoAlquiler.objects.filter(
        concepto__in=('renta', 'mora'),
        creado_en__gte=inicio,
    )
    if fin is not None:
        pagos = pagos.filter(creado_en__lt=fin)
    return pagos


def ingresos_periodo_actual():
    return pagos_de_ingresos(
        periodo_activo().inicio_periodo
    ).aggregate(total=Sum('monto', default=Decimal('0.00')))['total']
