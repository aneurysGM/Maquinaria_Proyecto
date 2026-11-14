from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.db import DatabaseError, transaction
from apps.inventario.models import Unidad
from apps.cuentas.models import permisos_panel
from .forms import MantenimientoForm
from .models import Mantenimiento
from .consultas import mantenimientos_abiertos
from django.utils import timezone

@login_required
def mantenimiento_lista(request):
    """Muestra el listado de unidades físicas y su estado actual respecto a mantenimiento."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido al personal autorizado.")

    if request.GET.get('atencion') == '1':
        return render(request, 'mantenimiento/mantenimiento_atencion.html', {
            'mantenimientos': mantenimientos_abiertos(), 'hoy': timezone.localdate(),
        })

    unidades = Unidad.objects.select_related('maquinaria__categoria').filter(activo=True, maquinaria__activo=True)
    consulta = request.GET.get('q', '').strip()
    
    if consulta:
        unidades = unidades.filter(
            Q(maquinaria__codigo__icontains=consulta)
            | Q(maquinaria__nombre__icontains=consulta)
            | Q(numero_serie__icontains=consulta)
        )
        
    return render(request, 'mantenimiento/mantenimiento_lista.html', {
        'unidades': unidades, 
        'consulta': consulta,
        'puede_registrar_mantenimiento': True
    })


@login_required
def mantenimiento_registrar(request):
    """Formulario para registrar una nueva orden de mantenimiento correctivo o preventivo."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido al personal autorizado.")

    unidad_preseleccionada = request.GET.get('unidad')
    initial_data = {'unidad': unidad_preseleccionada} if unidad_preseleccionada else {}

    if request.method == 'POST':
        form = MantenimientoForm(request.POST)
        if form.is_valid():
            try:
                mantenimiento = form.save(tecnico=request.user)
            except ValidationError as error:
                for msg in error.messages:
                    form.add_error(None, msg)
            except DatabaseError:
                form.add_error(None, 'No se pudo registrar el mantenimiento por un error de base de datos.')
            else:
                messages.success(request, 'Mantenimiento registrado con éxito. La unidad ha pasado a estado "En mantenimiento".')
                return redirect('mantenimiento:mantenimiento_historial', unidad_id=mantenimiento.unidad_id)
    else:
        form = MantenimientoForm(initial=initial_data)

    return render(request, 'mantenimiento/mantenimiento_form.html', {
        'form': form,
        'nombre_usuario': request.user.get_full_name() or request.user.email
    })


@login_required
def mantenimiento_historial(request, unidad_id):
    """Historial completo de intervenciones técnicas realizadas a una unidad física."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido.")

    unidad = get_object_or_404(Unidad.objects.select_related('maquinaria__categoria'), pk=unidad_id)
    mantenimientos = unidad.mantenimientos.select_related('tecnico')
    
    return render(request, 'mantenimiento/mantenimiento_historial.html', {
        'unidad': unidad, 
        'mantenimientos': mantenimientos,
        'puede_registrar_mantenimiento': True
    })

@login_required
@transaction.atomic
def mantenimiento_finalizar(request, unidad_id):
    """Finaliza el estado de mantenimiento de una unidad y la devuelve a 'Disponible'."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido al personal autorizado.")

    unidad = get_object_or_404(Unidad.objects.select_for_update(), pk=unidad_id)

    if unidad.estado != 'Mantenimiento':
        messages.error(request, 'Esta unidad no se encuentra en mantenimiento actualmente.')
        return redirect('mantenimiento:mantenimiento_historial', unidad_id=unidad.pk)

    # Cerrar la última orden de mantenimiento abierta
    mantenimiento_activo = unidad.mantenimientos.filter(fecha_fin__isnull=True).first()
    if mantenimiento_activo:
        mantenimiento_activo.fecha_fin = timezone.localdate()
        mantenimiento_activo.save(update_fields=['fecha_fin'])

    # Devolver unidad a disponible
    unidad.estado = 'Disponible'
    unidad.save(update_fields=['estado'])

    messages.success(request, f'La unidad #{unidad.numero_serie} ha finalizado su mantenimiento y ya se encuentra Disponible.')
    return redirect('mantenimiento:mantenimiento_historial', unidad_id=unidad.pk)
