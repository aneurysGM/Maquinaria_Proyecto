from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models import F, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from apps.alquileres.bloqueos import bloquear_unidad
from apps.cuentas.models import permisos_panel
from apps.mantenimiento.models import Mantenimiento
from .forms import (
    ActualizarOrdenForm,
    ChecklistForm,
    CierreOrdenForm,
    ComentarioOrdenForm,
    ConsumoRepuestoForm,
    EntradaRepuestoForm,
    RepuestoForm,
    SolicitudRepuestoFormSet,
)
from .models import (
    BorradorOrden,
    ComentarioOrden,
    ConsumoRepuesto,
    DetalleSolicitudRepuesto,
    EntradaRepuesto,
    PuntoChecklist,
    RegistroTrabajo,
    Repuesto,
    SolicitudRepuesto,
)


def _es_personal(usuario):
    permisos = permisos_panel(usuario)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied('Acceso restringido al personal técnico y administrativo.')
    return permisos.get('es_administrador', False)


def _requiere_tecnico(usuario):
    permisos = permisos_panel(usuario)
    if not permisos.get('es_tecnico'):
        raise PermissionDenied(
            'Solo el técnico asignado puede trabajar y registrar avances en la orden.'
        )


def _ordenes_visibles(usuario):
    ordenes = Mantenimiento.objects.select_related(
        'unidad__maquinaria__categoria', 'tecnico', 'registrado_por',
    )
    if not usuario.es_administrador:
        ordenes = ordenes.filter(tecnico=usuario)
    return ordenes


def _obtener_orden(usuario, mantenimiento_id, *, bloquear=False):
    orden = get_object_or_404(_ordenes_visibles(usuario), pk=mantenimiento_id)
    if bloquear:
        orden = get_object_or_404(
            Mantenimiento.objects.select_for_update().select_related('unidad'),
            pk=orden.pk,
        )
    return orden


def _mensaje_error(request, error):
    if isinstance(error, ValidationError):
        mensajes = error.messages
    else:
        mensajes = [
            'No se pudo guardar la operación por un error de base de datos. '
            'No se guardaron cambios; actualiza e inténtalo de nuevo.'
        ]
    for mensaje in mensajes:
        messages.error(request, mensaje)


@login_required(login_url='cuentas:login')
@require_safe
def orden_lista(request):
    administrador = _es_personal(request.user)
    ordenes = _ordenes_visibles(request.user)
    if request.GET.get('historial') != '1':
        ordenes = ordenes.filter(fecha_fin__isnull=True)
    consulta = request.GET.get('q', '').strip()
    if consulta:
        ordenes = ordenes.filter(
            Q(unidad__numero_serie__icontains=consulta)
            | Q(unidad__maquinaria__codigo__icontains=consulta)
            | Q(unidad__maquinaria__nombre__icontains=consulta)
        )
    ordenes = ordenes.order_by('fecha', 'pk')
    return render(request, 'ordenes_trabajo/lista.html', {
        'preventivos': ordenes.filter(tipo='Preventivo'),
        'correctivos': ordenes.filter(tipo='Correctivo'),
        'consulta': consulta,
        'mostrar_historial': request.GET.get('historial') == '1',
        'es_administrador': administrador,
    })


@login_required(login_url='cuentas:login')
@require_safe
def orden_detalle(request, mantenimiento_id):
    return _renderizar_detalle(request, mantenimiento_id)


def _renderizar_detalle(request, mantenimiento_id, formularios=None):
    administrador = _es_personal(request.user)
    orden = get_object_or_404(
        _ordenes_visibles(request.user).prefetch_related(
            'registros_trabajo__tecnico',
            'comentarios_tecnicos__autor',
            'puntos_checklist__revisado_por',
            'solicitudes_repuestos__detalles',
            'consumos_repuestos__repuesto',
        ),
        pk=mantenimiento_id,
    )
    checklist_existente = {
        punto.punto: {
            'resultado': punto.resultado,
            'observacion': punto.observacion,
        }
        for punto in orden.puntos_checklist.all()
    }
    borrador = BorradorOrden.objects.filter(mantenimiento=orden).first() if not administrador else None
    datos_borrador = borrador.datos if borrador else {}
    avance_inicial = {
        'estado': orden.estado if orden.estado != 'finalizada' else 'reparacion',
        'horas_trabajo': Decimal('0.0'),
        'horometro': orden.unidad.horas_uso,
        'dias_estimados': max((orden.fecha_estimada_fin - timezone.localdate()).days, 1)
        if orden.fecha_estimada_fin else None,
    }
    avance_inicial.update(datos_borrador.get('avance', {}))
    formularios = formularios or {
        'actualizar_form': ActualizarOrdenForm(
            initial=avance_inicial, prefix='avance', permitir_finalizada=True,
        ),
        'checklist_form': ChecklistForm(
            checklist_existente=checklist_existente,
            initial=datos_borrador.get('checklist', {}),
            prefix='checklist',
        ),
        'cierre_form': CierreOrdenForm(initial=datos_borrador.get('cierre', {}), prefix='cierre'),
    }
    return render(request, 'ordenes_trabajo/detalle.html', {
        'orden': orden,
        'es_administrador': administrador,
        **formularios,
        'hay_borrador': borrador is not None,
        'comentario_form': ComentarioOrdenForm(),
        'solicitud_formset': SolicitudRepuestoFormSet(prefix='repuestos'),
        'consumo_form': ConsumoRepuestoForm(),
        'hay_solicitudes_pendientes': orden.solicitudes_repuestos.filter(
            estado__in=('pendiente', 'aprobada'),
        ).exists(),
    })


def _registrar_avance(orden, unidad, usuario, form):
    horas_horometro = form.cleaned_data['horometro']
    if horas_horometro < unidad.horas_uso:
        raise ValidationError(
            f'El horómetro no puede ser menor que la lectura actual ({unidad.horas_uso} h).'
        )
    unidad.horas_uso = horas_horometro
    unidad.save(update_fields=['horas_uso', 'fecha_modificacion'])
    estado = form.cleaned_data['estado']
    if estado != 'finalizada':
        orden.estado = estado
    dias_estimados = form.cleaned_data['dias_estimados']
    orden.fecha_estimada_fin = (
        timezone.localdate() + timedelta(days=dias_estimados)
        if dias_estimados is not None else None
    )
    orden.save(update_fields=['estado', 'fecha_estimada_fin'])
    RegistroTrabajo.objects.create(
        mantenimiento=orden,
        tecnico=usuario,
        estado=estado,
        horas=form.cleaned_data['horas_trabajo'],
        observaciones=form.cleaned_data['observaciones'],
    )


def _guardar_checklist(orden, usuario, form):
    for punto, datos in form.resultados().items():
        PuntoChecklist.objects.update_or_create(
            mantenimiento=orden,
            punto=punto,
            defaults={**datos, 'revisado_por': usuario},
        )


def _finalizar_orden(orden, usuario, observaciones):
    if orden.estado == 'finalizada' or orden.fecha_fin is not None:
        raise ValidationError('La orden ya estaba finalizada.')
    checklist = {
        punto.punto
        for punto in orden.puntos_checklist.all()
        if punto.resultado in dict(PuntoChecklist.RESULTADOS)
    }
    if len(checklist) != len(PuntoChecklist.PUNTOS):
        raise ValidationError('Completa todos los puntos del checklist antes de finalizar.')
    if orden.solicitudes_repuestos.filter(estado__in=('pendiente', 'aprobada')).exists():
        raise ValidationError(
            'No puedes finalizar mientras haya solicitudes de repuestos pendientes '
            'o aprobadas sin recibir.'
        )

    unidad = bloquear_unidad(pk=orden.unidad_id)
    orden.estado = 'finalizada'
    orden.fecha_fin = timezone.localdate()
    orden.save(update_fields=['estado', 'fecha_fin'])
    RegistroTrabajo.objects.create(
        mantenimiento=orden,
        tecnico=usuario,
        estado='finalizada',
        horas=Decimal('0.0'),
        observaciones=observaciones,
    )
    quedan_ordenes = Mantenimiento.objects.filter(
        unidad=unidad, fecha_fin__isnull=True,
    ).exclude(pk=orden.pk).exists()
    entrega_activa = unidad.solicitudes_alquiler.filter(
        fecha_salida__isnull=False, fecha_retorno__isnull=True,
    ).exists()
    if not quedan_ordenes and not entrega_activa and unidad.estado == 'Mantenimiento':
        unidad.estado = 'Disponible'
        unidad.save(update_fields=['estado'])
    if unidad.intervalo_mantenimiento_horas is not None:
        unidad.proximo_mantenimiento_horas = (
            unidad.horas_uso + unidad.intervalo_mantenimiento_horas
        )
        unidad.save(update_fields=['proximo_mantenimiento_horas'])
    BorradorOrden.objects.filter(mantenimiento=orden).delete()


@login_required(login_url='cuentas:login')
@require_POST
def orden_informe(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    accion = request.POST.get('accion')
    if accion not in ('borrador', 'finalizar'):
        return HttpResponseBadRequest('La acción de la orden no es válida.')
    parcial = accion == 'borrador'
    formularios = {
        'actualizar_form': ActualizarOrdenForm(
            request.POST, prefix='avance', parcial=parcial, permitir_finalizada=True,
        ),
        'checklist_form': ChecklistForm(request.POST, prefix='checklist', parcial=parcial),
        'cierre_form': CierreOrdenForm(request.POST, prefix='cierre', parcial=parcial),
    }
    validos = [form.is_valid() for form in formularios.values()]
    if not all(validos):
        messages.error(request, 'Revisa los campos indicados; no se guardaron cambios.')
        return _renderizar_detalle(request, mantenimiento_id, formularios)

    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            if orden.fecha_fin is not None or orden.estado == 'finalizada':
                raise ValidationError('La orden ya está finalizada y no admite cambios.')
            if parcial:
                datos = {
                    form.prefix: {
                        nombre: request.POST.get(form.add_prefix(nombre), '')
                        for nombre in form.fields
                    }
                    for form in formularios.values()
                }
                BorradorOrden.objects.update_or_create(
                    mantenimiento=orden, defaults={'datos': datos},
                )
            else:
                unidad = bloquear_unidad(pk=orden.unidad_id)
                _registrar_avance(orden, unidad, request.user, formularios['actualizar_form'])
                _guardar_checklist(orden, request.user, formularios['checklist_form'])
                _finalizar_orden(orden, request.user, formularios['cierre_form'].cleaned_data['observaciones'])
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
        return _renderizar_detalle(request, mantenimiento_id, formularios)
    messages.success(
        request,
        'Borrador guardado; todavía no se ha enviado la orden.'
        if parcial else 'Orden finalizada y formulario enviado.',
    )
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def orden_actualizar(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    form = ActualizarOrdenForm(request.POST)
    if not form.is_valid():
        _mensaje_error(
            request,
            ValidationError([
                error for errors in form.errors.values() for error in errors
            ]),
        )
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)

    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            if orden.fecha_fin is not None or orden.estado == 'finalizada':
                raise ValidationError('La orden ya está finalizada y no admite cambios.')
            unidad = bloquear_unidad(pk=orden.unidad_id)
            _registrar_avance(orden, unidad, request.user, form)
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(request, 'Se actualizó el estado y la bitácora de la orden.')
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def orden_comentar(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    form = ComentarioOrdenForm(request.POST)
    if not form.is_valid():
        _mensaje_error(
            request,
            ValidationError([
                error for errores in form.errors.values() for error in errores
            ]),
        )
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)

    orden = get_object_or_404(_ordenes_visibles(request.user), pk=mantenimiento_id)
    if orden.fecha_fin is not None or orden.estado == 'finalizada':
        messages.error(request, 'No puedes agregar comentarios a una orden finalizada.')
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)

    ComentarioOrden.objects.create(
        mantenimiento=orden,
        autor=request.user,
        comentario=form.cleaned_data['comentario'],
    )
    messages.success(request, 'Comentario técnico registrado en la orden.')
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def orden_guardar_checklist(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            if orden.fecha_fin is not None or orden.estado == 'finalizada':
                raise ValidationError('La orden ya está finalizada.')
            form = ChecklistForm(request.POST)
            if not form.is_valid():
                raise ValidationError([
                    error for errors in form.errors.values() for error in errors
                ])
            _guardar_checklist(orden, request.user, form)
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(request, 'Se guardó el checklist completo de inspección.')
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def orden_finalizar(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    observaciones = request.POST.get('observaciones', '').strip()
    if not observaciones or len(observaciones) > 2000:
        messages.error(request, 'Escribe las observaciones finales (máximo 2000 caracteres).')
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)

    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            _finalizar_orden(orden, request.user, observaciones)
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(
            request,
            'Orden finalizada. Se actualizó el próximo servicio programado por horómetro.',
        )
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def orden_solicitar_repuestos(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    formset = SolicitudRepuestoFormSet(request.POST, prefix='repuestos')
    if not formset.is_valid():
        errores = [
            error
            for form_errors in formset.errors
            for errores_campo in form_errors.values()
            for error in errores_campo
        ]
        errores.extend(str(error) for error in formset.non_form_errors())
        _mensaje_error(
            request,
            ValidationError(errores or ['Revisa las piezas solicitadas.']),
        )
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)

    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            if orden.fecha_fin is not None:
                raise ValidationError('No puedes solicitar repuestos para una orden finalizada.')
            solicitud = SolicitudRepuesto.objects.create(
                mantenimiento=orden,
                solicitada_por=request.user,
            )
            for form in formset:
                if not form.cleaned_data:
                    continue
                DetalleSolicitudRepuesto.objects.create(
                    solicitud=solicitud,
                    **form.cleaned_data,
                )
            orden.estado = 'esperando_repuestos'
            orden.save(update_fields=['estado'])
            RegistroTrabajo.objects.create(
                mantenimiento=orden,
                tecnico=request.user,
                estado='esperando_repuestos',
                horas=Decimal('0.0'),
                observaciones='Se solicitó uno o más repuestos para esta orden.',
            )
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(
            request,
            'Solicitud de repuestos enviada al administrador para su gestión.',
        )
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_POST
def solicitud_repuesto_resolver(request, solicitud_id, accion):
    administrador = _es_personal(request.user)
    if not administrador:
        raise PermissionDenied('Solo el administrador puede gestionar solicitudes de repuestos.')
    try:
        with transaction.atomic():
            solicitud = get_object_or_404(
                SolicitudRepuesto.objects.select_for_update().select_related('mantenimiento'),
                pk=solicitud_id,
            )
            if accion == 'aprobar':
                if solicitud.estado != 'pendiente':
                    raise ValidationError('Solo se puede aprobar una solicitud pendiente.')
                solicitud.estado = 'aprobada'
                solicitud.resuelta_por = request.user
                solicitud.save(update_fields=['estado', 'resuelta_por'])
                mensaje = 'Solicitud de repuestos aprobada.'
            elif accion == 'recibir':
                if solicitud.estado != 'aprobada':
                    raise ValidationError('Primero debes aprobar la solicitud antes de registrarla como recibida.')
                detalles = list(solicitud.detalles.select_for_update().order_by('pk'))
                if not detalles:
                    raise ValidationError('La solicitud no tiene repuestos registrados.')
                for detalle in detalles:
                    repuesto = Repuesto.objects.select_for_update().filter(
                        codigo__iexact=detalle.codigo,
                    ).first()
                    if repuesto is None:
                        repuesto = Repuesto.objects.create(
                            codigo=detalle.codigo,
                            nombre=detalle.nombre,
                            unidad_medida=detalle.unidad_medida,
                            existencia=Decimal('0.00'),
                        )
                    elif repuesto.unidad_medida.casefold() != detalle.unidad_medida.casefold():
                        raise ValidationError(
                            f'La unidad de medida de {detalle.codigo} no coincide con el catálogo.'
                        )
                    Repuesto.objects.filter(pk=repuesto.pk).update(
                        existencia=F('existencia') + detalle.cantidad,
                    )
                    EntradaRepuesto.objects.create(
                        repuesto=repuesto,
                        solicitud=solicitud,
                        registrado_por=request.user,
                        cantidad=detalle.cantidad,
                    )
                    detalle.repuesto = repuesto
                    detalle.save(update_fields=['repuesto'])
                solicitud.estado = 'recibida'
                solicitud.resuelta_por = request.user
                solicitud.resuelta_en = timezone.now()
                solicitud.save(update_fields=['estado', 'resuelta_por', 'resuelta_en'])
                mensaje = 'Recepción registrada y existencias actualizadas.'
            elif accion == 'rechazar':
                if solicitud.estado not in ('pendiente', 'aprobada'):
                    raise ValidationError('Esta solicitud ya fue recibida o rechazada.')
                solicitud.estado = 'rechazada'
                solicitud.resuelta_por = request.user
                solicitud.resuelta_en = timezone.now()
                solicitud.save(update_fields=['estado', 'resuelta_por', 'resuelta_en'])
                mensaje = 'Solicitud de repuestos rechazada.'
            else:
                raise ValidationError('La acción de gestión no es válida.')
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(request, mensaje)
    return redirect(
        'ordenes_trabajo:detalle',
        mantenimiento_id=solicitud.mantenimiento_id,
    )


@login_required(login_url='cuentas:login')
@require_POST
def orden_registrar_consumo(request, mantenimiento_id):
    _requiere_tecnico(request.user)
    form = ConsumoRepuestoForm(request.POST)
    if not form.is_valid():
        _mensaje_error(
            request,
            ValidationError([
                error for errors in form.errors.values() for error in errors
            ]),
        )
        return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)
    try:
        with transaction.atomic():
            orden = _obtener_orden(request.user, mantenimiento_id, bloquear=True)
            if orden.fecha_fin is not None:
                raise ValidationError('No puedes registrar consumo en una orden finalizada.')
            repuesto_id = form.cleaned_data['repuesto'].pk
            cantidad = form.cleaned_data['cantidad']
            actualizado = Repuesto.objects.filter(
                pk=repuesto_id,
                activo=True,
                existencia__gte=cantidad,
            ).update(existencia=F('existencia') - cantidad)
            if not actualizado:
                raise ValidationError(
                    'La existencia cambió o no alcanza para esa cantidad. Actualiza e inténtalo de nuevo.'
                )
            ConsumoRepuesto.objects.create(
                mantenimiento=orden,
                repuesto_id=repuesto_id,
                registrado_por=request.user,
                cantidad=cantidad,
            )
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(request, 'Consumo registrado y existencia descontada.')
    return redirect('ordenes_trabajo:detalle', mantenimiento_id=mantenimiento_id)


@login_required(login_url='cuentas:login')
@require_safe
def repuesto_redireccion(request):
    return redirect('Repuestos_Inventario:lista')


@login_required(login_url='cuentas:login')
@require_safe
def repuesto_crear(request):
    if not request.user.es_administrador:
        raise PermissionDenied
    return render(request, 'ordenes_trabajo/repuesto_form.html', {
        'form': RepuestoForm(),
    })


@login_required(login_url='cuentas:login')
@require_POST
def repuesto_guardar(request):
    if not request.user.es_administrador:
        raise PermissionDenied
    form = RepuestoForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            'ordenes_trabajo/repuesto_form.html',
            {'form': form},
            status=400,
        )
    try:
        repuesto = form.save()
    except DatabaseError:
        form.add_error(None, 'No se pudo guardar el repuesto. Actualiza e inténtalo de nuevo.')
        return render(
            request,
            'ordenes_trabajo/repuesto_form.html',
            {'form': form},
            status=400,
        )
    messages.success(request, f'Repuesto {repuesto.codigo} registrado sin existencia inicial.')
    return redirect('ordenes_trabajo:repuestos')


@login_required(login_url='cuentas:login')
@require_POST
def repuesto_entrada(request, repuesto_id):
    if not request.user.es_administrador:
        raise PermissionDenied
    form = EntradaRepuestoForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            ' '.join(error for errors in form.errors.values() for error in errors),
        )
        return redirect('ordenes_trabajo:repuestos')
    cantidad = form.cleaned_data['cantidad']
    try:
        with transaction.atomic():
            repuesto = get_object_or_404(
                Repuesto.objects.select_for_update(),
                pk=repuesto_id,
                activo=True,
            )
            Repuesto.objects.filter(pk=repuesto.pk).update(
                existencia=F('existencia') + cantidad,
            )
            EntradaRepuesto.objects.create(
                repuesto=repuesto,
                registrado_por=request.user,
                cantidad=cantidad,
            )
    except (ValidationError, DatabaseError) as error:
        _mensaje_error(request, error)
    else:
        messages.success(request, 'Entrada registrada y existencia actualizada.')
    return redirect('ordenes_trabajo:repuestos')
