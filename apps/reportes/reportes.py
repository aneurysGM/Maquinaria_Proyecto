"""Reportes de lectura: pantalla y XLSX comparten filtros y filas."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .forms_reportes import (
    EntregasReporteForm, MantenimientosReporteForm, MaquinariaReporteForm, SolicitudesReporteForm,
)
from .datos import Mantenimiento, SolicitudAlquiler, Unidad
from .exportacion_excel import exportar_excel
from .roles import puede_ver_reportes

ZONA = ZoneInfo('America/Santo_Domingo')
REPORTES = {
    'maquinaria': {
        'titulo': 'Maquinaria', 'form': MaquinariaReporteForm,
        'descripcion': 'Unidades por código, nombre, serie, estado y ubicación; incluye unidades inactivas.',
    },
    'solicitudes': {
        'titulo': 'Solicitudes de alquiler', 'form': SolicitudesReporteForm,
        'descripcion': 'El período incluye solicitudes cuyas fechas coincidan total o parcialmente con el rango indicado.',
    },
    'entregas': {
        'titulo': 'Salidas y retornos', 'form': EntregasReporteForm,
        'descripcion': 'Entregas registradas en HU-09. El período filtra la fecha de salida en hora de Santo Domingo.',
    },
    'mantenimientos': {
        'titulo': 'Mantenimientos', 'form': MantenimientosReporteForm,
        'descripcion': 'Actividades registradas y total de sus costos. El período filtra la fecha del mantenimiento.',
    },
}


def nombre_usuario(usuario):
    if usuario is None:
        return 'No registrado (registro anterior)'
    nombre = usuario.get_full_name()
    return f'{nombre} ({usuario.email})' if nombre else usuario.email


def nombre_unidad(unidad):
    return f'{unidad.codigo} · {unidad.nombre} · Serie: {unidad.numero_serie} · #{unidad.pk}'


def fecha_movimiento(fecha):
    return timezone.localtime(fecha, ZONA) if fecha else None


def construir_reporte(tipo, datos):
    total = None
    if tipo == 'maquinaria':
        registros = Unidad.objects.select_related('maquinaria').order_by('maquinaria__codigo', 'numero_serie', 'id')
        if datos['q']:
            consulta = datos['q']
            registros = registros.filter(
                Q(maquinaria__codigo__icontains=consulta) | Q(maquinaria__nombre__icontains=consulta)
                | Q(numero_serie__icontains=consulta) | Q(ubicacion_actual__icontains=consulta)
            )
        if datos['estado']:
            registros = registros.filter(estado=datos['estado'])
        encabezados = ('Código', 'Nombre', 'Número de serie', 'Estado', 'Ubicación')
        filas = [(r.codigo, r.nombre, r.numero_serie, r.get_estado_display(), r.ubicacion_actual or '') for r in registros]
    elif tipo == 'solicitudes':
        registros = SolicitudAlquiler.objects.select_related('cliente', 'unidad__maquinaria').order_by('fecha_inicio', 'id')
        if datos['estado']:
            registros = registros.filter(estado=datos['estado'])
        if datos['cliente']:
            registros = registros.filter(cliente=datos['cliente'])
        # Intersección inclusiva entre el período solicitado y el rango consultado.
        if datos['desde']:
            registros = registros.filter(fecha_fin__gte=datos['desde'])
        if datos['hasta']:
            registros = registros.filter(fecha_inicio__lte=datos['hasta'])
        encabezados = ('Solicitud', 'Cliente', 'Unidad', 'Inicio solicitado', 'Fin solicitado', 'Estado')
        filas = [(str(r.pk), nombre_usuario(r.cliente), nombre_unidad(r.unidad), r.fecha_inicio, r.fecha_fin, r.estado) for r in registros]
    elif tipo == 'entregas':
        registros = SolicitudAlquiler.objects.filter(fecha_salida__isnull=False).select_related(
            'cliente', 'unidad__maquinaria', 'entregado_por', 'recibido_por',
        ).order_by('fecha_salida', 'id')
        if datos['situacion'] == 'pendiente':
            registros = registros.filter(fecha_retorno__isnull=True)
        elif datos['situacion'] == 'devuelta':
            registros = registros.filter(fecha_retorno__isnull=False)
        if datos['desde']:
            registros = registros.filter(fecha_salida__gte=datetime.combine(datos['desde'], time.min, tzinfo=ZONA))
        if datos['hasta'] and datos['hasta'] < date.max:
            fin_exclusivo = datetime.combine(datos['hasta']+timedelta(days=1), time.min, tzinfo=ZONA)
            registros = registros.filter(fecha_salida__lt=fin_exclusivo)
        encabezados = ('Solicitud', 'Cliente', 'Unidad', 'Salida (Santo Domingo)', 'Retorno (Santo Domingo)', 'Entregada por', 'Recibida por', 'Situación')
        filas = [(str(r.pk), nombre_usuario(r.cliente), nombre_unidad(r.unidad), fecha_movimiento(r.fecha_salida),
                  fecha_movimiento(r.fecha_retorno), nombre_usuario(r.entregado_por),
                  nombre_usuario(r.recibido_por) if r.recibido_por else '', r.estado_entrega) for r in registros]
    else:
        registros = Mantenimiento.objects.select_related('unidad__maquinaria', 'tecnico').order_by('fecha', 'id')
        if datos['desde']:
            registros = registros.filter(fecha__gte=datos['desde'])
        if datos['hasta']:
            registros = registros.filter(fecha__lte=datos['hasta'])
        if datos['unidad']:
            registros = registros.filter(unidad=datos['unidad'])
        if datos['tipo']:
            registros = registros.filter(tipo=datos['tipo'])
        registros = list(registros)
        # Decimal y exactamente las filas leídas: evita otra consulta que pueda
        # obtener un total diferente si se registra una actividad entre consultas.
        total = sum((r.costo for r in registros), Decimal('0.00'))
        encabezados = ('Unidad', 'Fecha', 'Tipo', 'Descripción', 'Responsable', 'Costo')
        filas = [(nombre_unidad(r.unidad), r.fecha, r.tipo, r.descripcion or '', nombre_usuario(r.tecnico), r.costo) for r in registros]
    return encabezados, filas, total


@login_required(login_url='cuentas:login')
@require_GET
@never_cache
def indice(request):
    if not puede_ver_reportes(request.user):
        raise PermissionDenied
    return render(request, 'reportes/reportes_indice.html', {'reportes': REPORTES})


@login_required(login_url='cuentas:login')
@require_GET
@never_cache
def reporte(request, tipo):
    if not puede_ver_reportes(request.user):
        raise PermissionDenied
    configuracion = REPORTES.get(tipo)
    if configuracion is None:
        raise Http404

    formato = request.GET.get('formato', 'html')
    csv_retirado = formato == 'csv'
    consultado = bool(request.GET)
    formulario = configuracion['form'](request.GET if consultado else None)
    valido = formulario.is_valid() and consultado
    if csv_retirado:
        formulario.add_error(None, 'La descarga CSV fue retirada. Utiliza Descargar Excel (.xlsx).')
        valido = False
    elif formato not in ('html', 'xlsx'):
        formulario.add_error(None, 'Formato de reporte inválido.')
        valido = False
    encabezados, filas, total = (), [], None
    if valido:
        encabezados, filas, total = construir_reporte(tipo, formulario.cleaned_data)
        if formato == 'xlsx':
            return exportar_excel(tipo, configuracion['titulo'], encabezados, filas, total)
    parametros = request.GET.copy()
    parametros.pop('formato', None)
    volver_url = request.path+('?' + parametros.urlencode() if parametros else '')
    parametros['formato'] = 'xlsx'
    return render(request, 'reportes/reporte.html', {
        'tipo': tipo, 'titulo': configuracion['titulo'], 'descripcion': configuracion['descripcion'],
        'form': formulario, 'filtrado_valido': valido, 'encabezados': encabezados, 'filas': filas,
        'total_costo': total, 'csv_retirado': csv_retirado, 'volver_url': volver_url,
        'exportar_excel_url': request.path+'?'+parametros.urlencode(),
    }, status=410 if csv_retirado else (400 if consultado and not valido else 200))
