from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Unidad

from .forms import TecnicoCreacionForm


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
