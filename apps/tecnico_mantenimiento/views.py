from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Unidad
from apps.mantenimiento.models import Mantenimiento

from .forms import TecnicoCreacionForm, TecnicoPerfilForm


@login_required(login_url='cuentas:login')
def dashboard(request):
    if not request.user.es_tecnico:
        raise PermissionDenied

    unidades_activas = Unidad.objects.filter(
        activo=True,
        maquinaria__activo=True,
    )
    ordenes_asignadas = Mantenimiento.objects.filter(
        tecnico=request.user,
        fecha_fin__isnull=True,
    ).select_related(
        'unidad__maquinaria',
    ).order_by('fecha', 'pk')
    return render(request, 'tecnico_mantenimiento/dashboard.html', {
        'cantidad_unidades': unidades_activas.count(),
        'unidades_mantenimiento': unidades_activas.filter(
            estado='Mantenimiento',
        ).count(),
        'cantidad_pendientes': ordenes_asignadas.filter(estado='pendiente').count(),
        'cantidad_diagnostico': ordenes_asignadas.filter(estado='diagnostico').count(),
        'cantidad_reparacion': ordenes_asignadas.filter(estado='reparacion').count(),
        'cantidad_esperando_repuestos': ordenes_asignadas.filter(estado='esperando_repuestos').count(),
        'unidades_destacadas': unidades_activas.select_related(
            'maquinaria__categoria',
        ).prefetch_related(
            'maquinaria__imagenes',
        ).order_by(
            '-maquinaria__fecha_modificacion',
        )[:6],
        'ordenes_preventivas': ordenes_asignadas.filter(tipo='Preventivo'),
        'ordenes_correctivas': ordenes_asignadas.filter(tipo='Correctivo'),
    })


@login_required(login_url='cuentas:login')
def lista(request):
    if not request.user.es_administrador:
        raise PermissionDenied

    tecnicos = UsuarioPersonalizado.objects.filter(
        rol=RolUsuario.TECNICO,
    ).order_by('first_name', 'email')
    return render(request, 'tecnico_mantenimiento/lista.html', {
        'tecnicos': tecnicos,
    })


@login_required(login_url='cuentas:login')
def crear(request):
    if not request.user.es_administrador:
        raise PermissionDenied

    if request.method == 'POST':
        form = TecnicoCreacionForm(request.POST)
        if form.is_valid():
            tecnico = form.save()
            messages.success(
                request,
                f'La cuenta técnica de {tecnico.get_full_name() or tecnico.email} fue creada.',
            )
            return redirect('tecnico_mantenimiento:lista')
    else:
        form = TecnicoCreacionForm()

    return render(request, 'tecnico_mantenimiento/crear.html', {
        'form': form,
    })


@login_required(login_url='cuentas:login')
def perfil(request, tecnico_id):
    if not request.user.es_administrador:
        raise PermissionDenied
    tecnico = get_object_or_404(UsuarioPersonalizado, pk=tecnico_id, rol=RolUsuario.TECNICO)
    form = TecnicoPerfilForm(request.POST if request.method == 'POST' else None, instance=tecnico)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Perfil técnico actualizado.')
        return redirect('tecnico_mantenimiento:perfil', tecnico_id=tecnico.pk)
    return render(request, 'tecnico_mantenimiento/perfil.html', {'tecnico': tecnico, 'form': form})


@login_required(login_url='cuentas:login')
@require_POST
def cambiar_estado(request, tecnico_id):
    if not request.user.es_administrador:
        raise PermissionDenied
    with transaction.atomic():
        tecnico = get_object_or_404(
            UsuarioPersonalizado.objects.select_for_update(), pk=tecnico_id, rol=RolUsuario.TECNICO,
        )
        if tecnico.is_superuser or tecnico.is_staff:
            messages.error(request, 'No se puede cambiar el estado de una cuenta con privilegios administrativos.')
        elif tecnico.is_active and Mantenimiento.objects.filter(tecnico=tecnico, fecha_fin__isnull=True).exists():
            messages.error(request, 'No se puede inactivar al técnico mientras tenga órdenes abiertas. Finalízalas primero.')
        else:
            tecnico.is_active = not tecnico.is_active
            tecnico.save(update_fields=['is_active'])
            messages.success(request, 'Estado de la cuenta técnica actualizado.')
    return redirect('tecnico_mantenimiento:lista')


@login_required(login_url='cuentas:login')
@require_POST
def eliminar(request, tecnico_id):
    if not request.user.es_administrador:
        raise PermissionDenied
    tecnico = get_object_or_404(UsuarioPersonalizado, pk=tecnico_id, rol=RolUsuario.TECNICO)
    if tecnico.is_superuser or tecnico.is_staff:
        messages.error(request, 'No se puede eliminar una cuenta con privilegios administrativos.')
    elif tecnico.maquinarias_registradas.exists():
        messages.error(request, 'El técnico tiene historial asociado y no se puede eliminar. Puedes inactivarlo.')
    else:
        try:
            tecnico.delete()
        except ProtectedError:
            messages.error(request, 'El técnico tiene historial asociado y no se puede eliminar. Puedes inactivarlo.')
        else:
            messages.success(request, 'Cuenta técnica eliminada.')
    return redirect('tecnico_mantenimiento:lista')
