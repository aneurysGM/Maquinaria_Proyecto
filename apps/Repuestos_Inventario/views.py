from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from apps.ordenes_trabajo.forms import EntradaRepuestoForm, RepuestoForm
from apps.ordenes_trabajo.models import Repuesto, SolicitudRepuesto


@login_required(login_url='cuentas:login')
@require_safe
def repuestos_lista(request):
    if not (request.user.es_administrador or request.user.es_tecnico):
        raise PermissionDenied('Solo el personal administrativo y técnico puede consultar repuestos.')

    es_administrador = request.user.es_administrador
    solicitudes = SolicitudRepuesto.objects.select_related(
        'mantenimiento__unidad__maquinaria',
        'solicitada_por',
    ).prefetch_related('detalles')
    if es_administrador:
        solicitudes = solicitudes.filter(estado__in=('pendiente', 'aprobada'))
    else:
        solicitudes = solicitudes.filter(solicitada_por=request.user)

    return render(request, 'Repuestos_Inventario/repuestos_lista.html', {
        'repuestos': Repuesto.objects.order_by('codigo'),
        'solicitudes': solicitudes.order_by('creada_en', 'pk'),
        'es_administrador': es_administrador,
    })


@login_required(login_url='cuentas:login')
@require_safe
def repuesto_crear(request):
    if not request.user.es_administrador:
        raise PermissionDenied
    return render(request, 'Repuestos_Inventario/repuesto_form.html', {
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
            'Repuestos_Inventario/repuesto_form.html',
            {'form': form},
            status=400,
        )
    try:
        repuesto = form.save()
    except DatabaseError:
        form.add_error(None, 'No se pudo guardar el repuesto. Actualiza e inténtalo de nuevo.')
        return render(
            request,
            'Repuestos_Inventario/repuesto_form.html',
            {'form': form},
            status=400,
        )
    messages.success(request, f'Repuesto {repuesto.codigo} registrado sin existencia inicial.')
    return redirect('Repuestos_Inventario:lista')


@login_required(login_url='cuentas:login')
@require_POST
def repuesto_entrada(request, repuesto_id):
    if not request.user.es_administrador:
        raise PermissionDenied
    form = EntradaRepuestoForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            ' '.join(error for errores in form.errors.values() for error in errores),
        )
        return redirect('Repuestos_Inventario:lista')
    try:
        with transaction.atomic():
            repuesto = get_object_or_404(Repuesto.objects.select_for_update(), pk=repuesto_id)
            Repuesto.objects.filter(pk=repuesto.pk).update(
                existencia=F('existencia') + form.cleaned_data['cantidad'],
            )
    except DatabaseError:
        messages.error(request, 'No se pudo registrar la entrada. Actualiza e inténtalo de nuevo.')
    else:
        messages.success(request, f'Se registró la entrada de {repuesto.codigo}.')
    return redirect('Repuestos_Inventario:lista')
