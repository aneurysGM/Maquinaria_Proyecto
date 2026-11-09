from calendar import monthrange
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.cuentas.models import permisos_panel
from apps.inventario.models import Unidad
from apps.ventas.models import PresupuestoAlquiler
from .forms import RetornoMaquinariaForm, SolicitudAlquilerForm
from .models import SolicitudAlquiler


def dias_del_plan(plan, cantidad):
    dias_por_plan = {'diario': 1, 'semanal': 7, 'mensual': 30}
    return dias_por_plan[plan] * cantidad


def sumar_seis_meses(fecha):
    mes = fecha.month + 5
    anio = fecha.year + (mes - 1) // 12
    mes = (mes - 1) % 12 + 1
    ultimo_dia = monthrange(anio, mes)[1]
    return fecha.replace(year=anio, month=mes, day=min(fecha.day, ultimo_dia))


@login_required
def solicitud_registrar(request, unidad_id):
    """Permite solicitar el alquiler de una unidad con un plan y duración."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_cliente') or permisos.get('es_administrador')):
        raise PermissionDenied(
            'No tienes autorización para realizar solicitudes de alquiler.'
        )

    unidad = get_object_or_404(
        Unidad.objects.select_related('maquinaria'),
        pk=unidad_id,
        activo=True,
        maquinaria__activo=True,
    )
    if unidad.estado != 'Disponible':
        messages.error(
            request,
            'Esta unidad no se encuentra disponible para alquilar en este momento.',
        )
        return redirect('inventario:maquinaria_lista')

    if request.method == 'POST':
        form = SolicitudAlquilerForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    solicitud = form.save(commit=False)
                    solicitud.cliente = request.user
                    solicitud.unidad = unidad
                    dias_alquiler = dias_del_plan(
                        solicitud.plan, solicitud.cantidad
                    )
                    solicitud.fecha_fin = solicitud.fecha_inicio + timedelta(
                        days=dias_alquiler - 1
                    )

                    cruce = SolicitudAlquiler.objects.filter(
                        unidad=unidad,
                        estado='Aprobada',
                        fecha_inicio__lte=solicitud.fecha_fin,
                        fecha_fin__gte=solicitud.fecha_inicio,
                    ).exists()
                    if cruce:
                        raise ValidationError(
                            'Ya existe un alquiler aprobado para esta unidad '
                            'en las fechas seleccionadas.'
                        )

                    solicitud.save()
                    campo_tarifa = {
                        'diario': 'tarifa_diaria',
                        'semanal': 'tarifa_semanal',
                        'mensual': 'tarifa_mensual',
                    }[solicitud.plan]
                    tarifa_periodo = getattr(unidad.maquinaria, campo_tarifa)
                    presupuesto = PresupuestoAlquiler.objects.create(
                        solicitud=solicitud,
                        tarifa_periodo=tarifa_periodo,
                        importe_renta=tarifa_periodo * solicitud.cantidad,
                        deposito_garantia=unidad.maquinaria.deposito_garantia,
                    )
            except ValidationError as error:
                for mensaje in error.messages:
                    form.add_error(None, mensaje)
            except DatabaseError:
                form.add_error(
                    None,
                    'No se pudo guardar la solicitud debido a un error de base de datos.',
                )
            else:
                messages.success(
                    request,
                    'Solicitud enviada. El presupuesto estimado está disponible para consulta.',
                )
                return redirect(
                    'ventas:presupuesto_detalle',
                    presupuesto_id=presupuesto.pk,
                )
    else:
        form = SolicitudAlquilerForm()

    return render(
        request,
        'alquileres/solicitud_form.html',
        {'form': form, 'unidad': unidad},
    )


@login_required
def solicitud_lista(request):
    """Clientes ven sus solicitudes; administradores ven todas."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_cliente')):
        raise PermissionDenied(
            'No tienes autorización para consultar solicitudes.'
        )

    solicitudes = SolicitudAlquiler.objects.select_related(
        'unidad__maquinaria',
        'cliente',
        'revisado_por',
        'presupuesto',
    )
    if permisos.get('es_cliente'):
        solicitudes = solicitudes.filter(cliente=request.user)

    for solicitud in solicitudes:
        solicitud.mora_estimada = (
            solicitud.presupuesto.calcular_mora(solicitud.dias_atraso_actual)
            if solicitud.politica_mora_aplica
            and solicitud.dias_atraso_actual
            and hasattr(solicitud, 'presupuesto')
            else 0
        )

    return render(
        request,
        'alquileres/solicitud_lista.html',
        {'solicitudes': solicitudes},
    )


@login_required
@transaction.atomic
def solicitud_resolver(request, solicitud_id):
    """Permite al administrador aprobar o rechazar una solicitud pendiente."""
    if not request.user.es_administrador:
        raise PermissionDenied(
            'Solo los administradores pueden resolver solicitudes.'
        )
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud = get_object_or_404(
        SolicitudAlquiler.objects.select_for_update().select_related(
            'unidad__maquinaria'
        ),
        pk=solicitud_id,
    )
    if solicitud.estado != 'Pendiente':
        messages.warning(
            request,
            'Esta solicitud ya había sido revisada previamente.',
        )
        return redirect('alquileres:solicitud_lista')

    decision = request.POST.get('decision')
    if decision not in ('Aprobada', 'Rechazada'):
        messages.error(request, 'Decisión inválida.')
        return redirect('alquileres:solicitud_lista')

    try:
        if decision == 'Aprobada':
            if solicitud.fecha_inicio < timezone.localdate():
                raise ValidationError(
                    'No se puede aprobar una solicitud cuya fecha de inicio ya pasó.'
                )
            unidad = solicitud.unidad
            if (
                not unidad.activo
                or not unidad.maquinaria.activo
                or unidad.estado != 'Disponible'
            ):
                raise ValidationError(
                    'La unidad física ya no está disponible para aprobación.'
                )
            cruce = SolicitudAlquiler.objects.filter(
                unidad=unidad,
                estado='Aprobada',
                fecha_inicio__lte=solicitud.fecha_fin,
                fecha_fin__gte=solicitud.fecha_inicio,
            ).exclude(pk=solicitud.pk).exists()
            if cruce:
                raise ValidationError(
                    'Existe un conflicto de fechas con otra solicitud aprobada.'
                )

        solicitud.estado = decision
        solicitud.revisado_por = request.user
        solicitud.fecha_revision = timezone.now()
        solicitud.save(update_fields=[
            'estado', 'revisado_por', 'fecha_revision'
        ])
        messages.success(
            request,
            f'La solicitud #{solicitud.pk} ha sido {decision.lower()} correctamente.',
        )
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    except DatabaseError:
        messages.error(request, 'Ocurrió un error al procesar la base de datos.')
    return redirect('alquileres:solicitud_lista')


@login_required
@transaction.atomic
def solicitud_registrar_salida(request, solicitud_id):
    if not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden registrar entregas.')
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud = get_object_or_404(
        SolicitudAlquiler.objects.select_for_update().select_related('unidad'),
        pk=solicitud_id,
    )
    if solicitud.estado != 'Aprobada' or solicitud.fecha_salida:
        messages.error(
            request,
            'Esta solicitud no está disponible para registrar una salida.',
        )
        return redirect('alquileres:solicitud_lista')
    if solicitud.fecha_inicio > timezone.localdate():
        messages.error(
            request,
            'No se puede entregar la maquinaria antes de la fecha programada.',
        )
        return redirect('alquileres:solicitud_lista')

    unidad = Unidad.objects.select_for_update().select_related(
        'maquinaria'
    ).get(pk=solicitud.unidad_id)
    if (
        not unidad.activo
        or not unidad.maquinaria.activo
        or unidad.estado != 'Disponible'
    ):
        messages.error(request, 'La unidad ya no está disponible para entregar.')
        return redirect('alquileres:solicitud_lista')

    solicitud.fecha_salida = timezone.now()
    solicitud.entregado_por = request.user
    solicitud.save(update_fields=['fecha_salida', 'entregado_por'])
    unidad.estado = 'Alquilado'
    unidad.save(update_fields=['estado'])
    messages.success(
        request,
        f'Se registró la salida de la solicitud #{solicitud.pk}.',
    )
    return redirect('alquileres:solicitud_lista')


@login_required
@transaction.atomic
def solicitud_registrar_retorno(request, solicitud_id):
    if not request.user.es_administrador:
        raise PermissionDenied(
            'Solo los administradores pueden registrar devoluciones.'
        )
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud = get_object_or_404(
        SolicitudAlquiler.objects.select_for_update().select_related(
            'cliente', 'unidad__maquinaria'
        ),
        pk=solicitud_id,
    )
    if (
        solicitud.estado != 'Aprobada'
        or not solicitud.fecha_salida
        or solicitud.fecha_retorno
    ):
        messages.error(
            request,
            'Esta solicitud no está disponible para registrar un retorno.',
        )
        return redirect('alquileres:solicitud_lista')

    form = RetornoMaquinariaForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            'Indica correctamente las horas de uso para registrar el retorno.',
        )
        return redirect('alquileres:solicitud_lista')

    unidad = Unidad.objects.select_for_update().get(pk=solicitud.unidad_id)
    horas_actualizadas = form.cleaned_data['horas_uso_actualizadas']
    if horas_actualizadas < unidad.horas_uso:
        messages.error(
            request,
            'Las horas del horómetro no pueden ser menores al registro actual.',
        )
        return redirect('alquileres:solicitud_lista')

    fecha_retorno = timezone.now()
    dias_atraso = max(
        (timezone.localtime(fecha_retorno).date() - solicitud.fecha_fin).days,
        0,
    )
    solicitud.fecha_retorno = fecha_retorno
    solicitud.recibido_por = request.user
    solicitud.dias_atraso = dias_atraso
    solicitud.observaciones_retorno = form.cleaned_data['observaciones_retorno']
    solicitud.save(update_fields=[
        'fecha_retorno',
        'recibido_por',
        'dias_atraso',
        'observaciones_retorno',
    ])

    unidad.estado = 'Disponible'
    unidad.horas_uso = horas_actualizadas
    unidad.save(update_fields=['estado', 'horas_uso'])

    presupuesto = getattr(solicitud, 'presupuesto', None)
    if presupuesto and solicitud.politica_mora_aplica:
        presupuesto.mora_total = presupuesto.calcular_mora(dias_atraso)
        presupuesto.mora_actualizada_en = fecha_retorno
        presupuesto.save(update_fields=['mora_total', 'mora_actualizada_en'])

    if dias_atraso:
        mora_total = presupuesto.mora_total if presupuesto else '0.00'
        messages.warning(
            request,
            f'La devolución tuvo {dias_atraso} día(s) de atraso. '
            f'Mora calculada: ${mora_total}.',
        )
    else:
        messages.success(request, 'La maquinaria fue devuelta dentro del plazo.')

    infracciones_anteriores = SolicitudAlquiler.objects.filter(
        cliente=solicitud.cliente,
        politica_mora_aplica=True,
        dias_atraso__gt=3,
    ).exclude(pk=solicitud.pk).count()
    if dias_atraso > 3 and infracciones_anteriores >= 1:
        cliente = solicitud.cliente
        cliente.is_active = False
        cliente.suspension_hasta = sumar_seis_meses(timezone.localdate())
        cliente.save(update_fields=['is_active', 'suspension_hasta'])
        messages.error(
            request,
            f'La cuenta de {cliente.email} quedó suspendida hasta '
            f'{cliente.suspension_hasta:%d/%m/%Y} por su segunda devolución '
            'con más de 3 días de atraso.',
        )
    elif dias_atraso > 3:
        messages.warning(
            request,
            'Advertencia: esta es la primera devolución con más de 3 días de atraso. '
            'Una segunda infracción de este tipo suspenderá la cuenta por 6 meses.',
        )
    return redirect('alquileres:solicitud_lista')
