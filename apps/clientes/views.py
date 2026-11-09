from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.views.generic import DetailView, ListView

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
        clientes = UsuarioPersonalizado.objects.filter(rol=RolUsuario.CLIENTE)

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
        )
        return context
