from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cuentas.models import permisos_panel
from apps.inventario.models import Unidad
from .consultas import mantenimientos_abiertos
from .forms import MantenimientoForm
from .models import Mantenimiento

@login_required
def mantenimiento_lista(request):
    """Muestra el listado de unidades físicas y su estado actual respecto a mantenimiento."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido al personal autorizado.")

    if request.GET.get('atencion') == '1':
        abiertos = mantenimientos_abiertos()
        if not permisos.get('es_administrador'):
            abiertos = abiertos.filter(tecnico=request.user)
        return render(request, 'mantenimiento/mantenimiento_atencion.html', {
            'mantenimientos': abiertos, 'hoy': timezone.localdate(),
        })

    unidades = Unidad.objects.select_related(
        'maquinaria__categoria', 'maquinaria__marca',
    ).prefetch_related(
        'maquinaria__imagenes',
    ).filter(
        activo=True,
        maquinaria__activo=True,
    )
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
        form = MantenimientoForm(request.POST, usuario=request.user)
        if 'filtrar' not in request.POST and form.is_valid():
            try:
                mantenimiento = form.save(request=request)
            except ValidationError as error:
                for msg in error.messages:
                    form.add_error(None, msg)
            except DatabaseError:
                form.add_error(None, 'No se pudo registrar el mantenimiento por un error de base de datos.')
            else:
                messages.success(request, 'Mantenimiento registrado con éxito. La unidad ha pasado a estado "En mantenimiento".')
                return redirect(
                    'ordenes_trabajo:detalle',
                    mantenimiento_id=mantenimiento.pk,
                )
    else:
        form = MantenimientoForm(initial=initial_data, usuario=request.user)

    return render(request, 'mantenimiento/mantenimiento_form.html', {
        'form': form,
        'nombre_usuario': request.user.get_full_name() or request.user.email,
        'tecnicos_disponibles': [
            {'id': tecnico.pk, 'especialidad': tecnico.especialidad,
             'nombre': form.fields['tecnico_responsable'].label_from_instance(tecnico)}
            for tecnico in form.tecnicos_disponibles
        ] if request.user.es_administrador else [],
    })


@login_required
def mantenimiento_historial(request, unidad_id):
    """Historial completo de intervenciones técnicas realizadas a una unidad física."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido.")

    unidad = get_object_or_404(Unidad.objects.select_related('maquinaria__categoria'), pk=unidad_id)
    mantenimientos = unidad.mantenimientos.select_related(
        'tecnico', 'registrado_por',
    ).prefetch_related(
        'registros_trabajo',
        'comentarios_tecnicos__autor',
        'puntos_checklist',
        'consumos_repuestos__repuesto',
    )
    
    return render(request, 'mantenimiento/mantenimiento_historial.html', {
        'unidad': unidad, 
        'mantenimientos': mantenimientos,
        'puede_registrar_mantenimiento': True,
        'ordenes_activas': unidad.mantenimientos.filter(fecha_fin__isnull=True),
    })


@login_required
@require_POST
def mantenimiento_finalizar(request, unidad_id):
    """Redirige al cierre controlado de una orden específica."""
    permisos = permisos_panel(request.user)
    if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
        raise PermissionDenied("Acceso restringido al personal autorizado.")

    unidad = get_object_or_404(Unidad, pk=unidad_id)
    messages.warning(
        request,
        'Selecciona la orden específica y complétala desde su detalle para conservar '
        'la bitácora, el checklist y el horómetro.',
    )
    return redirect('mantenimiento:mantenimiento_historial', unidad_id=unidad.pk)
