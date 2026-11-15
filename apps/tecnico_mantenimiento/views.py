from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Unidad

from .forms import TecnicoCreacionForm, TecnicoPerfilForm


@login_required(login_url='cuentas:login')
def dashboard(request):
    if not request.user.es_tecnico:
        raise PermissionDenied

    unidades_activas = Unidad.objects.filter(
        activo=True,
        maquinaria__activo=True,
    )
    return render(request, 'tecnico_mantenimiento/dashboard.html', {
        'cantidad_unidades': unidades_activas.count(),
        'unidades_mantenimiento': unidades_activas.filter(
            estado='Mantenimiento',
        ).count(),
        'unidades_destacadas': unidades_activas.select_related(
            'maquinaria__categoria',
        ).prefetch_related(
            'maquinaria__imagenes',
        ).order_by(
            '-maquinaria__fecha_modificacion',
        )[:6],
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
