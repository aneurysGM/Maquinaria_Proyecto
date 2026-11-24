import calendar
from datetime import date, datetime, time, timedelta
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.ventas.models import PagoAlquiler
from .models import CierreMensual


CONCEPTOS_INGRESO = ('renta', 'mora')


def periodo_activo():
    return CierreMensual.objects.get(activo=True)


def pagos_de_ingresos(inicio, fin=None):
    pagos = PagoAlquiler.objects.filter(
        concepto__in=CONCEPTOS_INGRESO,
        creado_en__gte=inicio,
    )
    if fin is not None:
        pagos = pagos.filter(creado_en__lt=fin)
    return pagos


def ingresos_periodo_actual():
    return pagos_de_ingresos(
        periodo_activo().inicio_periodo
    ).aggregate(total=Sum('monto', default=0))['total']


def _inicio_local(fecha):
    return timezone.make_aware(
        datetime.combine(fecha, time.min),
        timezone.get_current_timezone(),
    )


def rango_mes(anio, mes):
    inicio_fecha = date(anio, mes, 1)
    if mes == 12:
        siguiente_fecha = date(anio + 1, 1, 1)
    else:
        siguiente_fecha = date(anio, mes + 1, 1)
    return _inicio_local(inicio_fecha), _inicio_local(siguiente_fecha)


def semanas_del_mes(anio, mes):
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    limites = ((1, 7), (8, 14), (15, 21), (22, ultimo_dia))
    semanas = []
    for numero, (dia_inicio, dia_fin) in enumerate(limites, start=1):
        desde = date(anio, mes, dia_inicio)
        hasta = date(anio, mes, dia_fin)
        semanas.append({
            'numero': numero,
            'desde': desde,
            'hasta': hasta,
            'inicio': _inicio_local(desde),
            'fin': _inicio_local(hasta + timedelta(days=1)),
        })
    return semanas


def pagos_de_mes(anio, mes):
    inicio, fin = rango_mes(anio, mes)
    return _pagos_detallados().filter(creado_en__gte=inicio, creado_en__lt=fin)


def pagos_de_semana(anio, mes, semana):
    intervalo = next(
        (item for item in semanas_del_mes(anio, mes) if item['numero'] == semana),
        None,
    )
    if intervalo is None:
        raise ValueError('La semana debe estar entre 1 y 4.')
    return _pagos_detallados().filter(
        creado_en__gte=intervalo['inicio'],
        creado_en__lt=intervalo['fin'],
    )


def _pagos_detallados():
    return PagoAlquiler.objects.select_related(
        'presupuesto__solicitud__cliente',
        'presupuesto__solicitud__unidad__maquinaria',
        'registrado_por',
    ).prefetch_related(
        'presupuesto__pagos',
        'presupuesto__reembolsos_deposito',
    ).order_by('creado_en', 'pk')


def resumen_pagos(pagos):
    return pagos.aggregate(
        cantidad_pagos=Count('pk'),
        ingresos=Sum(
            'monto',
            filter=Q(concepto__in=CONCEPTOS_INGRESO),
            default=0,
        ),
        depositos=Sum(
            'monto',
            filter=Q(concepto='deposito'),
            default=0,
        ),
        total_recibido=Sum('monto', default=0),
    )


def meses_disponibles():
    actual = timezone.localdate()
    meses = {(actual.year, actual.month)}

    for fecha in PagoAlquiler.objects.datetimes(
        'creado_en',
        'month',
        tzinfo=timezone.get_current_timezone(),
    ):
        meses.add((fecha.year, fecha.month))

    cierres = CierreMensual.objects.values_list('inicio_periodo', 'cerrado_en')
    for inicio, cierre in cierres.iterator():
        for fecha in (inicio, cierre):
            if fecha is not None:
                local = timezone.localtime(fecha)
                meses.add((local.year, local.month))

    primero = CierreMensual.objects.order_by(
        'inicio_periodo'
    ).values_list('inicio_periodo', flat=True).first()
    if primero is not None:
        desde = timezone.localtime(primero).date().replace(day=1)
        hasta = actual.replace(day=1)
        while desde <= hasta:
            meses.add((desde.year, desde.month))
            if desde.month == 12:
                desde = date(desde.year + 1, 1, 1)
            else:
                desde = date(desde.year, desde.month + 1, 1)

    resultado = []
    for anio, mes in sorted(meses, reverse=True):
        resumen = resumen_pagos(pagos_de_mes(anio, mes))
        if (anio, mes) == (actual.year, actual.month):
            estado = 'En curso'
        elif (anio, mes) < (actual.year, actual.month):
            estado = 'Histórico'
        else:
            estado = 'Próximo'
        resultado.append({
            'anio': anio,
            'mes': mes,
            'fecha': date(anio, mes, 1),
            'estado': estado,
            **resumen,
        })
    return resultado
