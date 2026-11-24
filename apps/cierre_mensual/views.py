from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .consultas import (
    meses_disponibles,
    pagos_de_semana,
    resumen_pagos,
    semanas_del_mes,
)
from apps.reportes.exportacion_excel import CONTENT_TYPE
from .servicios import cerrar_periodo


def _verificar_administrador(request):
    if not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden consultar cierres.')


def _obtener_mes(anio, mes):
    if not 1 <= anio <= 9998 or not 1 <= mes <= 12:
        raise Http404
    try:
        date(anio, mes, 1)
    except ValueError as error:
        raise Http404 from error

    return next(
        (
            item for item in meses_disponibles()
            if item['anio'] == anio and item['mes'] == mes
        ),
        None,
    )


@login_required(login_url='cuentas:login')
@never_cache
def historial_mensual(request):
    _verificar_administrador(request)
    return render(request, 'cierre_mensual/historial.html', {
        'meses': meses_disponibles(),
    })


@login_required(login_url='cuentas:login')
@never_cache
def detalle_mes(request, anio, mes):
    _verificar_administrador(request)
    periodo = _obtener_mes(anio, mes)
    if periodo is None:
        raise Http404

    semanas = semanas_del_mes(anio, mes)
    for semana in semanas:
        semana['resumen'] = resumen_pagos(
            pagos_de_semana(anio, mes, semana['numero'])
        )
    return render(request, 'cierre_mensual/mes.html', {
        'periodo': periodo,
        'semanas': semanas,
    })


@login_required(login_url='cuentas:login')
@never_cache
def detalle_semana(request, anio, mes, semana):
    _verificar_administrador(request)
    periodo = _obtener_mes(anio, mes)
    if periodo is None:
        raise Http404

    intervalo = next(
        (item for item in semanas_del_mes(anio, mes) if item['numero'] == semana),
        None,
    )
    if intervalo is None:
        raise Http404

    pagos_query = pagos_de_semana(anio, mes, semana)
    resumen = resumen_pagos(pagos_query)
    filas = []
    for pago in pagos_query:
        presupuesto = pago.presupuesto
        pagos_presupuesto = list(presupuesto.pagos.all())
        reembolsos = list(presupuesto.reembolsos_deposito.all())
        filas.append({
            'pago': pago,
            'total_presupuesto': presupuesto.importe_total_actual,
            'total_pagado': sum(
                (item.monto for item in pagos_presupuesto),
                0,
            ),
            'saldo': presupuesto.saldo_pendiente_actual,
            'deposito_reembolsado': sum(
                (item.monto for item in reembolsos),
                0,
            ),
        })

    return render(request, 'cierre_mensual/semana.html', {
        'periodo': periodo,
        'intervalo': intervalo,
        'filas': filas,
        'resumen': resumen,
    })


@login_required(login_url='cuentas:login')
@require_POST
def cerrar_mes(request):
    _verificar_administrador(request)

    resultado = cerrar_periodo()
    respuesta = HttpResponse(resultado.contenido, content_type=CONTENT_TYPE)
    respuesta['Content-Disposition'] = (
        f'attachment; filename="{resultado.nombre_archivo}"'
    )
    respuesta['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    respuesta['Pragma'] = 'no-cache'
    return respuesta
