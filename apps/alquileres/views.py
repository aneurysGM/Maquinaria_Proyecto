from datetime import timedelta
from functools import partial, wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from apps.cuentas.models import DireccionCliente, permisos_panel
from apps.inventario.models import Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from .bloqueos import bloquear_unidad
from .forms import (
    RetornoMaquinariaForm, SolicitudAlquilerForm, SolicitudAplazarForm,
    SolicitudFiltroForm, DireccionEntregaForm,
)
from .models import SolicitudAlquiler
from .notificaciones import notificar_vencimiento
from .reservas import (
    liberar_unidad_si_no_reservada,
    puede_aprobar_reserva,
    cruces_confirmados, periodos_ocupados,
    solicitudes_con_pago_inicial_completo,
)


def dias_del_plan(plan, cantidad):
    dias_por_plan = {'diario': 1, 'semanal': 7, 'mensual': 30}
    return max(dias_por_plan[plan] * cantidad, 1)


def bloquear_movimiento(solicitud_id):
    # La subconsulta evita una lectura previa al bloqueo de escritura en SQLite.
    referencia = SolicitudAlquiler.objects.filter(pk=solicitud_id).values('unidad_id')
    try:
        unidad = bloquear_unidad(pk__in=referencia)
    except Unidad.DoesNotExist:
        get_object_or_404(SolicitudAlquiler, pk=solicitud_id)
        raise ValidationError('La unidad de la solicitud ya no existe.')
    solicitud = get_object_or_404(SolicitudAlquiler.objects.select_for_update(), pk=solicitud_id)
    if solicitud.unidad_id != unidad.pk:
        raise ValidationError('La unidad de la solicitud cambió. Actualiza el listado.')
    return solicitud, unidad


def movimiento_atomico(vista):
    """Revierte todo el movimiento antes de comunicar un error de guardado."""
    @wraps(vista)
    def ejecutar(request, *args, **kwargs):
        try:
            with transaction.atomic():
                return vista(request, *args, **kwargs)
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        except DatabaseError:
            messages.error(request, 'No se pudo guardar la operación. No se guardaron cambios; actualiza e inténtalo de nuevo.')
        return redirect('alquileres:solicitud_lista')
    return ejecutar


def unidad_disponible(unidad):
    return unidad.activo and unidad.maquinaria.activo and unidad.estado in ('Disponible', 'Alquilado')


def solicitudes_consultables(usuario):
    permisos = permisos_panel(usuario)
    solicitudes = SolicitudAlquiler.objects.select_related(
        'unidad__maquinaria', 'cliente', 'revisado_por',
        'entregado_por', 'recibido_por', 'presupuesto',
    ).prefetch_related('presupuesto__pagos')
    if permisos.get('es_administrador'):
        return solicitudes
    if permisos.get('es_cliente'):
        return solicitudes.filter(cliente=usuario)
    raise PermissionDenied('No tienes autorización para consultar solicitudes.')


def filtrar_solicitudes(solicitudes, datos):
    consulta = datos['q']
    codigo_exacto = datos.get('codigo_exacto', '')
    if codigo_exacto and codigo_exacto.casefold() == consulta.casefold():
        solicitudes = solicitudes.filter(unidad__maquinaria__codigo__iexact=codigo_exacto)
    elif consulta:
        solicitudes = solicitudes.alias(
            nombre_cliente=Concat('cliente__first_name', Value(' '), 'cliente__last_name'),
        )
        coincidencias = (
            Q(cliente__email__icontains=consulta) | Q(nombre_cliente__icontains=consulta)
            | Q(unidad__maquinaria__codigo__icontains=consulta)
            | Q(unidad__maquinaria__nombre__icontains=consulta)
            | Q(unidad__numero_serie__icontains=consulta)
        )
        numero = consulta.removeprefix('#')
        if numero.isascii() and numero.isdecimal() and int(numero) <= 9223372036854775807:
            coincidencias |= Q(pk=int(numero))
        solicitudes = solicitudes.filter(coincidencias)
    if datos['estado']:
        solicitudes = solicitudes.filter(estado=datos['estado'])
    if datos['desde']:
        solicitudes = solicitudes.filter(fecha_fin__gte=datos['desde'])
    if datos['hasta']:
        solicitudes = solicitudes.filter(fecha_inicio__lte=datos['hasta'])
    return solicitudes


@login_required(login_url='cuentas:login')
def solicitud_registrar(request, unidad_id):
    """Permite solicitar el alquiler de una unidad con un plan y duración."""
    permisos = permisos_panel(request.user)
    if not permisos.get('es_cliente') or permisos.get('es_administrador'):
        raise PermissionDenied(
            'No tienes autorización para realizar solicitudes de alquiler.'
        )

    try:
        unidad = get_object_or_404(
            Unidad.objects.select_related('maquinaria'),
            pk=unidad_id,
            activo=True,
            maquinaria__activo=True,
        )
    except DatabaseError:
        messages.error(request, 'No se pudo consultar la unidad. Actualiza e inténtalo de nuevo.')
        return redirect('alquileres:solicitud_lista')
    if not unidad_disponible(unidad):
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
                    unidad = bloquear_unidad(pk=unidad_id)
                    if not unidad_disponible(unidad):
                        raise ValidationError('La unidad ya no está disponible para alquilar.')
                    solicitud = form.save(commit=False)
                    solicitud.cliente = request.user
                    solicitud.unidad = unidad
                    dias_alquiler = dias_del_plan(
                        solicitud.plan, solicitud.cantidad
                    )
                    try:
                        solicitud.fecha_fin = solicitud.fecha_inicio + timedelta(days=dias_alquiler - 1)
                    except OverflowError as error:
                        raise ValidationError('La duración del alquiler excede el rango de fechas.') from error

                    cruce = cruces_confirmados(unidad.pk, solicitud.fecha_inicio, solicitud.fecha_fin).exists()
                    if cruce:
                        raise ValidationError(
                            'La disponibilidad cambió o el período está ocupado por una reserva confirmada. '
                            'Elige otras fechas para el período completo del plan.'
                        )
                    if SolicitudAlquiler.objects.filter(
                        unidad=unidad, cliente=request.user, estado='Pendiente',
                        fecha_inicio=solicitud.fecha_inicio, fecha_fin=solicitud.fecha_fin,
                    ).exists():
                        raise ValidationError('Ya tienes una solicitud pendiente para esta unidad y estas fechas.')

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
        plan = request.GET.get('plan', '')
        if plan not in dict(SolicitudAlquiler.PLANES):
            plan = ''
        form = SolicitudAlquilerForm(initial={'plan': plan, 'cantidad': 1})

    return render(
        request,
        'alquileres/solicitud_form.html',
        {'form': form, 'unidad': unidad, 'periodos_ocupados': periodos_ocupados(unidad.pk), 'hoy': timezone.localdate().isoformat()},
    )


@login_required(login_url='cuentas:login')
@require_safe
def solicitud_codigos(request):
    """Sugiere únicamente códigos con solicitudes visibles bajo los filtros actuales."""
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied
    form = SolicitudFiltroForm(request.GET)
    if not form.is_valid():
        return JsonResponse({'codigos': []}, status=400)
    datos = form.cleaned_data.copy()
    consulta = datos['q']
    if not consulta:
        return JsonResponse({'codigos': []})
    datos.update(q='', codigo_exacto='')
    solicitudes = filtrar_solicitudes(solicitudes_consultables(request.user), datos)
    codigos = solicitudes.filter(unidad__maquinaria__codigo__icontains=consulta).order_by(
        'unidad__maquinaria__codigo',
    ).values_list('unidad__maquinaria__codigo', flat=True).distinct()
    unicos = {}
    for codigo in codigos:
        unicos.setdefault(codigo.casefold(), codigo)
    exacto = unicos.get(consulta.casefold())
    return JsonResponse({'codigos': [exacto] if exacto else list(unicos.values())})


@login_required(login_url='cuentas:login')
@require_safe
def solicitud_lista(request):
    """Clientes ven sus solicitudes; administradores ven todas."""
    solicitudes = solicitudes_consultables(request.user)
    filtros = None
    if request.user.es_administrador:
        filtros = SolicitudFiltroForm(request.GET)
        solicitudes = filtrar_solicitudes(solicitudes, filtros.cleaned_data) if filtros.is_valid() else solicitudes.none()

    return render(
        request,
        'alquileres/solicitud_lista.html',
        {
            'solicitudes': solicitudes,
            'filtros': filtros,
            'hoy': timezone.localdate().isoformat(),
        },
    )


@login_required(login_url='cuentas:login')
@require_safe
def solicitud_detalle(request, solicitud_id):
    solicitud = get_object_or_404(solicitudes_consultables(request.user), pk=solicitud_id)
    return render(
        request,
        'alquileres/solicitud_detalle.html',
        {'solicitud': solicitud, 'hoy': timezone.localdate().isoformat()},
    )


@login_required(login_url='cuentas:login')
@require_POST
@movimiento_atomico
def solicitud_avisar_vencimiento(request, solicitud_id):
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied('Solo el administrador puede enviar este aviso.')

    solicitud, _unidad = bloquear_movimiento(solicitud_id)
    destino = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        destino = reverse('alquileres:solicitud_lista')

    if solicitud.estado_cliente != 'Vencido':
        messages.warning(request, 'Solo se puede enviar este aviso para una solicitud vencida.')
        return redirect(destino)

    solicitud.fecha_aviso_vencimiento = timezone.now()
    solicitud.save(update_fields=['fecha_aviso_vencimiento'])
    enlace = request.build_absolute_uri(reverse('alquileres:solicitud_lista'))
    transaction.on_commit(partial(
        messages.success, request, 'El aviso quedó guardado en Mis alquileres del cliente.',
    ))
    transaction.on_commit(partial(notificar_vencimiento, solicitud, enlace, request=request))
    return redirect(destino)


@login_required(login_url='cuentas:login')
@require_http_methods(['GET', 'POST'])
def solicitud_direccion_entrega(request, solicitud_id):
    if not permisos_panel(request.user).get('es_cliente') or request.user.es_administrador:
        raise PermissionDenied('Solo el cliente titular puede confirmar la dirección de entrega.')
    solicitud = get_object_or_404(solicitudes_consultables(request.user), pk=solicitud_id)
    if not solicitud.pendiente_direccion_entrega:
        messages.warning(request, 'La dirección solo se puede confirmar después del pago inicial y antes de la salida; una vez confirmada se conserva en el alquiler.')
        return redirect('alquileres:solicitud_detalle', solicitud_id=solicitud.pk)

    form = DireccionEntregaForm(
        request.POST if request.method == 'POST' else None,
        cliente=request.user, tipo=request.GET.get('tipo'),
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                # Mismo orden de bloqueo que el pago y la salida. Relee el estado.
                solicitud, _unidad = bloquear_movimiento(solicitud_id)
                if solicitud.cliente_id != request.user.pk:
                    raise Http404
                if not solicitud.pendiente_direccion_entrega:
                    raise ValidationError('El alquiler ya no está pendiente de dirección. Vuelve a su detalle.')
                datos = form.cleaned_data
                if datos['tipo'] == 'guardada':
                    direccion = DireccionCliente.objects.select_for_update().filter(
                        pk=datos['direccion_guardada'].pk, cliente=request.user,
                    ).first()
                    if direccion is None:
                        raise ValidationError('La dirección guardada ya no existe. Elige otra dirección o escribe una nueva.')
                    texto, referencia, nombre = direccion.direccion, direccion.referencia, direccion.nombre
                    if not texto.strip():
                        raise ValidationError('La dirección guardada está vacía. Corrígela en Mis direcciones.')
                else:
                    texto, referencia = datos['direccion'], datos['referencia']
                    nombre = datos['nombre'] if datos['guardar'] else ''
                    if datos['guardar']:
                        DireccionCliente.objects.create(
                            cliente=request.user, nombre=nombre, direccion=texto, referencia=referencia,
                        )
                solicitud.direccion_entrega = texto
                solicitud.referencia_entrega = referencia
                solicitud.nombre_direccion_entrega = nombre
                solicitud.fecha_direccion_confirmada = timezone.now()
                solicitud.save(update_fields=[
                    'direccion_entrega', 'referencia_entrega',
                    'nombre_direccion_entrega', 'fecha_direccion_confirmada',
                ])
        except ValidationError as error:
            form.add_error(None, error)
        except DatabaseError:
            form.add_error(None, 'No se guardaron cambios. Actualiza e inténtalo de nuevo.')
        else:
            messages.success(request, 'Dirección de entrega confirmada. La entrega está pendiente.')
            return redirect('alquileres:solicitud_detalle', solicitud_id=solicitud.pk)
    return render(request, 'alquileres/direccion_entrega_form.html', {'solicitud': solicitud, 'form': form})


@login_required(login_url='cuentas:login')
@require_safe
def entrega_lista(request):
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied
    estado = request.GET.get('estado', 'programadas')
    if estado not in ('programadas', 'pendientes', 'atrasadas', 'devueltas', 'todas'):
        return HttpResponseBadRequest('Filtro de entregas inválido.')
    hoy = timezone.localdate()
    salidas_programadas = solicitudes_con_pago_inicial_completo(
        solicitudes_consultables(request.user).filter(
            estado='Aprobada',
            fecha_salida__isnull=True,
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
        )
    )
    entregas_base = solicitudes_consultables(request.user).filter(
        fecha_salida__isnull=False,
    )
    entregas_atrasadas = entregas_base.filter(
        fecha_retorno__isnull=True,
        fecha_fin__lt=hoy,
    )
    if estado == 'programadas':
        entregas = salidas_programadas
    elif estado == 'atrasadas':
        entregas = entregas_atrasadas
    elif estado == 'pendientes':
        entregas = entregas_base.filter(fecha_retorno__isnull=True)
    elif estado == 'devueltas':
        entregas = entregas_base.filter(fecha_retorno__isnull=False)
    else:
        entregas = entregas_base
    return render(
        request,
        'alquileres/entrega_lista.html',
        {
            'entregas': entregas.order_by('-fecha_salida', '-id'),
            'estado': estado,
            'salidas_programadas_count': salidas_programadas.count(),
            'entregas_atrasadas_count': entregas_atrasadas.count(),
        },
    )


@login_required(login_url='cuentas:login')
@movimiento_atomico
def solicitud_resolver(request, solicitud_id):
    """Permite al administrador aprobar o rechazar una solicitud pendiente."""
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied(
            'Solo los administradores pueden resolver solicitudes.'
        )
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud, unidad = bloquear_movimiento(solicitud_id)
    if solicitud.estado != 'Pendiente':
        messages.warning(
            request,
            'Esta solicitud ya había sido revisada previamente.',
        )
        return redirect('alquileres:solicitud_lista')
    if solicitud.fecha_aviso_disponibilidad is not None:
        messages.warning(
            request,
            'El cliente debe responder al aviso de disponibilidad antes de resolver esta solicitud.',
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
            if not puede_aprobar_reserva(solicitud, unidad):
                raise ValidationError(
                    'La unidad física ya no está disponible para aprobación.'
                )

        motivo = request.POST.get('motivo_rechazo', '').strip()
        if decision == 'Rechazada' and (not motivo or len(motivo) > 1000):
            raise ValidationError('Escribe un motivo de rechazo de hasta 1000 caracteres.')

        solicitud.estado = decision
        solicitud.revisado_por = request.user
        fecha_revision = timezone.now()
        solicitud.fecha_revision = fecha_revision
        solicitud.motivo_rechazo = motivo if decision == 'Rechazada' else ''
        solicitud.save(update_fields=[
            'estado', 'revisado_por', 'fecha_revision', 'motivo_rechazo'
        ])
        if decision == 'Rechazada':
            liberar_unidad_si_no_reservada(unidad, solicitud.pk)
        transaction.on_commit(partial(
            messages.success, request,
            f'La solicitud #{solicitud.pk} ha sido {decision.lower()} correctamente.',
        ))
    except ValidationError as error:
        for mensaje in error.messages:
            messages.error(request, mensaje)
    return redirect('alquileres:solicitud_lista')


@login_required(login_url='cuentas:login')
@movimiento_atomico
def solicitud_responder_disponibilidad(request, solicitud_id):
    if not request.user.es_cliente:
        raise PermissionDenied('Solo el cliente titular puede responder este aviso.')
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud, _unidad = bloquear_movimiento(solicitud_id)
    if solicitud.cliente_id != request.user.pk:
        raise Http404

    accion = request.POST.get('accion')
    if accion == 'cancelar':
        if not solicitud.puede_cancelar_cliente:
            if PagoAlquiler.objects.filter(presupuesto__solicitud=solicitud).exists():
                messages.error(
                    request,
                    'No puedes cancelar en línea porque esta solicitud tiene pagos registrados. '
                    'Contacta al administrador para revisar el reembolso.',
                )
            else:
                messages.warning(request, 'Esta solicitud ya no se puede cancelar.')
            return redirect('alquileres:solicitud_lista')

        solicitud.estado = 'Cancelada'
        solicitud.aplazada = False
        solicitud.fecha_aviso_disponibilidad = None
        solicitud.motivo_disponibilidad = ''
        solicitud.save(update_fields=[
            'estado', 'aplazada', 'fecha_aviso_disponibilidad',
            'motivo_disponibilidad',
        ])
        messages.success(
            request,
            'La solicitud fue cancelada.',
        )
        return redirect('alquileres:solicitud_lista')

    if accion != 'aplazar':
        messages.error(request, 'La respuesta seleccionada no es válida.')
        return redirect('alquileres:solicitud_lista')

    if (
        solicitud.estado not in ('Pendiente', 'Aprobada')
        or solicitud.fecha_aviso_disponibilidad is None
        or solicitud.aplazada
        or solicitud.fecha_salida is not None
    ):
        messages.warning(request, 'Esta solicitud ya no espera una respuesta.')
        return redirect('alquileres:solicitud_lista')

    form = SolicitudAplazarForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            ' '.join(error for errores in form.errors.values() for error in errores),
        )
        return redirect('alquileres:solicitud_lista')

    fecha_inicio = form.cleaned_data['fecha_inicio']
    duracion = solicitud.fecha_fin - solicitud.fecha_inicio
    try:
        fecha_fin = fecha_inicio + duracion
    except OverflowError as error:
        raise ValidationError('La duración del alquiler excede el rango de fechas.') from error

    if cruces_confirmados(
        solicitud.unidad_id, fecha_inicio, fecha_fin, excluir=solicitud.pk,
    ).exists():
        raise ValidationError(
            'La fecha elegida coincide con una reserva confirmada. Elige otra fecha.'
        )

    solicitud.fecha_inicio = fecha_inicio
    solicitud.fecha_fin = fecha_fin
    solicitud.estado = 'Pendiente'
    solicitud.aplazada = False
    solicitud.fecha_aviso_disponibilidad = None
    solicitud.motivo_disponibilidad = ''
    solicitud.fecha_revision = None
    solicitud.revisado_por = None
    solicitud.fecha_confirmacion = None
    solicitud.save(update_fields=[
        'fecha_inicio', 'fecha_fin', 'estado', 'aplazada',
        'fecha_aviso_disponibilidad', 'motivo_disponibilidad',
        'fecha_revision', 'revisado_por', 'fecha_confirmacion',
    ])
    messages.success(
        request,
        'Se actualizaron las fechas solicitadas. La solicitud quedó pendiente de revisión.',
    )
    return redirect('alquileres:solicitud_lista')


@login_required(login_url='cuentas:login')
@movimiento_atomico
def solicitud_registrar_salida(request, solicitud_id):
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied('Solo los administradores pueden registrar entregas.')
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud, unidad = bloquear_movimiento(solicitud_id)
    if solicitud.estado != 'Aprobada' or solicitud.fecha_salida:
        messages.error(
            request,
            'Esta solicitud no está disponible para registrar una salida.',
        )
        return redirect('alquileres:solicitud_lista')
    if not solicitud.pago_inicial_completo:
        messages.error(request, 'Completa la renta y el depósito inicial para confirmar la reserva antes de entregar.')
        return redirect('alquileres:solicitud_lista')
    if not solicitud.direccion_entrega_confirmada:
        messages.error(request, 'Pendiente de dirección de entrega: el cliente debe confirmarla antes de registrar la salida.')
        return redirect('alquileres:solicitud_detalle', solicitud_id=solicitud.pk)
    # Las fechas proceden del servidor, como en el flujo original de Aneurys.
    fecha_salida = timezone.now()
    if solicitud.fecha_inicio > timezone.localdate(fecha_salida):
        messages.error(
            request,
            'No se puede entregar la maquinaria antes de la fecha programada.',
        )
        return redirect('alquileres:solicitud_lista')

    if (
        not unidad.activo
        or not unidad.maquinaria.activo
        or unidad.estado not in ('Disponible', 'Alquilado')
        or SolicitudAlquiler.objects.filter(
            unidad=unidad, fecha_salida__isnull=False, fecha_retorno__isnull=True,
        ).exclude(pk=solicitud.pk).exists()
    ):
        messages.error(request, 'La unidad ya no está disponible para entregar.')
        return redirect('alquileres:solicitud_lista')

    solicitud.fecha_salida = fecha_salida
    solicitud.entregado_por = request.user
    solicitud.save(update_fields=['fecha_salida', 'entregado_por'])
    unidad.estado = 'Alquilado'
    unidad.save(update_fields=['estado'])
    messages.success(
        request,
        f'Se registró la salida de la solicitud #{solicitud.pk}.',
    )
    return redirect('alquileres:solicitud_lista')


@login_required(login_url='cuentas:login')
@movimiento_atomico
def solicitud_registrar_retorno(request, solicitud_id):
    if not permisos_panel(request.user).get('es_administrador'):
        raise PermissionDenied(
            'Solo los administradores pueden registrar devoluciones.'
        )
    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    solicitud, unidad = bloquear_movimiento(solicitud_id)
    if (
        solicitud.estado != 'Aprobada'
        or not solicitud.fecha_salida
        or solicitud.fecha_retorno
        or unidad.estado != 'Alquilado'
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
            ' '.join(error for errores in form.errors.values() for error in errores),
        )
        return redirect('alquileres:solicitud_lista')

    horas_actualizadas = (
        form.cleaned_data['horas_uso_actualizadas']
        if form.cleaned_data['horas_uso_actualizadas'] is not None
        else unidad.horas_uso
    )
    if horas_actualizadas < unidad.horas_uso:
        messages.error(
            request,
            'Las horas del horómetro no pueden ser menores al registro actual.',
        )
        return redirect('alquileres:solicitud_lista')

    fecha_retorno = timezone.now()
    if fecha_retorno < solicitud.fecha_salida:
        messages.error(request, 'La fecha de retorno no puede ser anterior a la salida.')
        return redirect('alquileres:solicitud_lista')
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

    liberar_unidad_si_no_reservada(unidad, solicitud.pk)
    unidad.horas_uso = horas_actualizadas
    unidad.save(update_fields=['horas_uso'])

    from .reservas import programar_siguiente_solicitud_aplazada
    siguiente = programar_siguiente_solicitud_aplazada(
        unidad, fecha_retorno, actor=request.user, request=request,
    )
    if siguiente is not None:
        transaction.on_commit(partial(
            messages.success,
            request,
            f'La solicitud #{siguiente.pk} fue programada del '
            f'{siguiente.fecha_inicio:%d/%m/%Y} al {siguiente.fecha_fin:%d/%m/%Y}.',
        ))

    presupuesto = getattr(solicitud, 'presupuesto', None)
    if presupuesto and solicitud.politica_mora_aplica:
        presupuesto.mora_total = presupuesto.calcular_mora(dias_atraso)
        presupuesto.mora_actualizada_en = fecha_retorno
        presupuesto.save(update_fields=['mora_total', 'mora_actualizada_en'])

    if dias_atraso:
        mensaje = f'La devolución tuvo {dias_atraso} día(s) de atraso.'
        if presupuesto and solicitud.politica_mora_aplica:
            mensaje += f' Mora calculada: ${presupuesto.mora_total}.'
        transaction.on_commit(partial(
            messages.warning,
            request,
            mensaje,
        ))
    else:
        transaction.on_commit(partial(
            messages.success, request, 'La maquinaria fue devuelta dentro del plazo.',
        ))

    return redirect('alquileres:solicitud_lista')
