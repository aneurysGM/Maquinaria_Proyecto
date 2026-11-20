from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, ListView
from django.views.decorators.http import require_POST

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.alquileres.models import SolicitudAlquiler


class AdministradorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'cuentas:login'

    def test_func(self):
        return self.request.user.es_administrador


class ClienteListaView(AdministradorRequiredMixin, ListView):
    model = UsuarioPersonalizado
    template_name = 'clientes/cliente_lista.html'
    context_object_name = 'clientes'
    paginate_by = 20

    def get_queryset(self):
        clientes = UsuarioPersonalizado.objects.filter(
            rol=RolUsuario.CLIENTE
        )

        estado = self.request.GET.get('estado', '')
        if estado == 'activos':
            clientes = clientes.filter(is_active=True)
        elif estado == 'inactivos':
            clientes = clientes.filter(is_active=False)

        busqueda = self.request.GET.get('q', '').strip()
        if busqueda:
            clientes = clientes.filter(
                Q(email__icontains=busqueda)
                | Q(first_name__icontains=busqueda)
                | Q(last_name__icontains=busqueda)
                | Q(telefono__icontains=busqueda)
            )

        return clientes.order_by('first_name', 'last_name', 'email')


class ClienteDetalleView(AdministradorRequiredMixin, DetailView):
    model = UsuarioPersonalizado
    template_name = 'clientes/cliente_detalle.html'
    context_object_name = 'cliente'

    def get_queryset(self):
        return UsuarioPersonalizado.objects.filter(rol=RolUsuario.CLIENTE)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['solicitudes'] = SolicitudAlquiler.objects.filter(
            cliente=self.object
        ).select_related(
            'unidad__maquinaria__categoria',
            'revisado_por',
            'entregado_por',
            'recibido_por',
            'presupuesto',
        ).order_by('-fecha_creacion', '-id')
        context['devoluciones_tardias'] = context['solicitudes'].filter(
            politica_mora_aplica=True,
            dias_atraso__gt=0,
        ).count()
        context['alquileres_vencidos'] = context['solicitudes'].filter(
            politica_mora_aplica=True,
            fecha_salida__isnull=False,
            fecha_retorno__isnull=True,
            fecha_fin__lt=timezone.localdate(),
        ).count()
        for solicitud in context['solicitudes']:
            solicitud.mora_estimada = (
                solicitud.presupuesto.calcular_mora(solicitud.dias_atraso_actual)
                if solicitud.politica_mora_aplica
                and solicitud.dias_atraso_actual
                and hasattr(solicitud, 'presupuesto')
                else 0
            )
        return context


@require_POST
def cliente_cambiar_estado(request, pk):
    if not request.user.is_authenticated or not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden cambiar el estado de clientes.')

    cliente = get_object_or_404(UsuarioPersonalizado, pk=pk, rol=RolUsuario.CLIENTE)
    accion = request.POST.get('accion')
    if accion == 'inactivar':
        motivo = request.POST.get('motivo', '').strip()
        if not motivo:
            messages.error(request, 'Debes indicar el motivo de la inactivación.')
            return redirect('clientes:cliente_detalle', pk=cliente.pk)
        cliente.is_active = False
        cliente.motivo_inactivacion = motivo
        messages.success(request, 'El cliente fue inactivado manualmente.')
    elif accion == 'activar':
        cliente.is_active = True
        cliente.motivo_inactivacion = ''
        messages.success(request, 'El cliente fue activado nuevamente.')
    else:
        messages.error(request, 'La acción solicitada no es válida.')
        return redirect('clientes:cliente_detalle', pk=cliente.pk)

    cliente.save(update_fields=['is_active', 'motivo_inactivacion'])
    return redirect('clientes:cliente_detalle', pk=cliente.pk)
