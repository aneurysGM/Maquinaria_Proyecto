from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.inventario.models import Unidad
from apps.cuentas.models import permisos_panel
from .forms import SolicitudAlquilerForm
from .models import SolicitudAlquiler


@login_required
def solicitud_registrar(request, unidad_id):
    """Permite a un cliente o administrador solicitar el alquiler de una unidad física específica."""
    permisos = permisos_panel(request.user)
    
    # Validamos si el usuario tiene permiso para solicitar alquileres
    if not (permisos.get('es_cliente') or permisos.get('es_administrador')):
        raise PermissionDenied("No tienes autorización para realizar solicitudes de alquiler.")

    unidad = get_object_or_404(
        Unidad.objects.select_related('maquinaria'), 
        pk=unidad_id, 
        activo=True, 
        maquinaria__activo=True
    )

    if unidad.estado != 'Disponible':
        messages.error(request, 'Esta unidad no se encuentra disponible para alquilar en este momento.')
        return redirect('inventario:maquinaria_lista')

    if request.method == 'POST':
        form = SolicitudAlquilerForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    solicitud = form.save(commit=False)
                    solicitud.cliente = request.user
                    solicitud.unidad = unidad
                    
                    # Validar cruce de fechas si ya hay otra aprobada
                    cruce = SolicitudAlquiler.objects.filter(
                        unidad=unidad,
                        estado='Aprobada',
                        fecha_inicio__lte=solicitud.fecha_fin,
                        fecha_fin__gte=solicitud.fecha_inicio
                    ).exists()
                    
                    if cruce:
                        raise ValidationError('Ya existe un alquiler aprobado para esta unidad en las fechas seleccionadas.')
                    
                    solicitud.save()
            except ValidationError as error:
                for msg in error.messages:
                    form.add_error(None, msg)
            except DatabaseError:
                form.add_error(None, 'No se pudo guardar la solicitud debido a un error de base de datos.')
            else:
                messages.success(request, '¡Solicitud de alquiler enviada exitosamente! El administrador la revisará pronto.')
                return redirect('alquileres:solicitud_lista')
    else:
        form = SolicitudAlquilerForm()

    return render(request, 'alquileres/solicitud_form.html', {'form': form, 'unidad': unidad})


@login_required
def solicitud_lista(request):
    """Bandeja de solicitudes. Los clientes ven las suyas; los administradores ven todas."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_cliente')):
        raise PermissionDenied("No tienes autorización para consultar solicitudes.")

    solicitudes = SolicitudAlquiler.objects.select_related(
        'unidad__maquinaria', 'cliente', 'revisado_por'
    )

    if permisos.get('es_cliente'):
        solicitudes = solicitudes.filter(cliente=request.user)

    return render(request, 'alquileres/solicitud_lista.html', {'solicitudes': solicitudes})


@login_required
@transaction.atomic
def solicitud_resolver(request, solicitud_id):
    """Permite al administrador aprobar o rechazar una solicitud pendiente."""
    permisos = permisos_panel(request.user)
    if not permisos.get('es_administrador'):
        raise PermissionDenied("Solo los administradores pueden resolver solicitudes.")

    if request.method != 'POST':
        return redirect('alquileres:solicitud_lista')

    decision = request.POST.get('decision')
    if decision not in ('Aprobada', 'Rechazada'):
        messages.error(request, 'Decisión inválida.')
        return redirect('alquileres:solicitud_lista')

    solicitud = get_object_or_404(
        SolicitudAlquiler.objects.select_for_update().select_related('unidad__maquinaria'), 
        pk=solicitud_id
    )

    if solicitud.estado != 'Pendiente':
        messages.warning(request, 'Esta solicitud ya había sido revisada previamente.')
        return redirect('alquileres:solicitud_lista')

    try:
        if decision == 'Aprobada':
            if solicitud.fecha_inicio < timezone.localdate():
                raise ValidationError('No se puede aprobar una solicitud cuya fecha de inicio ya pasó.')
            
            unidad = solicitud.unidad
            if not unidad.activo or not unidad.maquinaria.activo or unidad.estado != 'Disponible':
                raise ValidationError('La unidad física ya no está disponible para aprobación.')

            # Comprobar cruces definitivos
            cruce = SolicitudAlquiler.objects.filter(
                unidad=unidad,
                estado='Aprobada',
                fecha_inicio__lte=solicitud.fecha_fin,
                fecha_fin__gte=solicitud.fecha_inicio
            ).exists()

            if cruce:
                raise ValidationError('Existe un conflicto de fechas con otra solicitud aprobada.')

        solicitud.estado = decision
        solicitud.revisado_por = request.user
        solicitud.fecha_revision = timezone.now()
        solicitud.save(update_fields=['estado', 'revisado_por', 'fecha_revision'])

        messages.success(request, f'La solicitud #{solicitud.id} ha sido {decision.lower()} correctamente.')

    except ValidationError as error:
        for msg in error.messages:
            messages.error(request, msg)
    except DatabaseError:
        messages.error(request, 'Ocurrió un error al procesar la base de datos.')

    return redirect('alquileres:solicitud_lista')