from dataclasses import dataclass
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from apps.reportes.exportacion_excel import exportar_excel
from .consultas import pagos_de_ingresos
from .models import CierreMensual


@dataclass(frozen=True)
class ResultadoCierre:
    contenido: bytes
    nombre_archivo: str
    archivo_servidor: str
    total: Decimal
    cantidad_pagos: int


def _nombre_archivo(inicio, fin):
    inicio_local = timezone.localtime(inicio)
    fin_local = timezone.localtime(fin)
    return (
        f'ingresos_{inicio_local:%Y%m%d_%H%M%S}_'
        f'{fin_local:%Y%m%d_%H%M%S}.xlsx'
    )


def _crear_excel(pagos):
    encabezados = (
        'Pago',
        'Fecha y hora',
        'Presupuesto',
        'Solicitud',
        'Cliente',
        'Maquinaria',
        'Código',
        'Número de serie',
        'Concepto',
        'Monto (RD$)',
        'Método',
        'Referencia',
        'Registrado por',
    )
    filas = []
    for pago in pagos:
        solicitud = pago.presupuesto.solicitud
        maquinaria = solicitud.unidad.maquinaria
        registrado_por = pago.registrado_por
        nombre = registrado_por.get_full_name() or registrado_por.email
        filas.append((
            pago.pk,
            timezone.localtime(pago.creado_en),
            pago.presupuesto_id,
            solicitud.pk,
            solicitud.cliente.get_full_name() or solicitud.cliente.email,
            maquinaria.nombre,
            maquinaria.codigo,
            solicitud.unidad.numero_serie,
            pago.get_concepto_display(),
            pago.monto,
            pago.get_metodo_display(),
            pago.referencia,
            nombre,
        ))

    total = sum((pago.monto for pago in pagos), Decimal('0.00'))
    respuesta = exportar_excel(
        'cierre_mensual',
        'Cierre mensual de ingresos',
        encabezados,
        filas,
        total,
        etiqueta_total='Total ingresos',
    )
    return respuesta.content, total


def cerrar_periodo(*, origen='manual', guardar_en_servidor=False):
    with transaction.atomic():
        periodo = CierreMensual.objects.select_for_update().get(activo=True)
        cierre = timezone.now()
        pagos = list(
            pagos_de_ingresos(periodo.inicio_periodo, cierre)
            .select_related(
                'presupuesto__solicitud__cliente',
                'presupuesto__solicitud__unidad__maquinaria',
                'registrado_por',
            )
            .order_by('creado_en', 'pk')
        )
        contenido, total = _crear_excel(pagos)
        nombre_archivo = _nombre_archivo(periodo.inicio_periodo, cierre)
        archivo_servidor = ''
        if guardar_en_servidor:
            archivo_servidor = default_storage.save(
                f'cierres_mensuales/{nombre_archivo}',
                ContentFile(contenido),
            )

        periodo.cerrado_en = cierre
        periodo.activo = False
        periodo.origen = origen
        periodo.archivo_excel = archivo_servidor
        periodo.save(update_fields=(
            'cerrado_en',
            'activo',
            'origen',
            'archivo_excel',
        ))
        CierreMensual.objects.create(inicio_periodo=cierre)

    return ResultadoCierre(
        contenido=contenido,
        nombre_archivo=nombre_archivo,
        archivo_servidor=archivo_servidor,
        total=total,
        cantidad_pagos=len(pagos),
    )
