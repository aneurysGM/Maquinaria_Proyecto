from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q
from django.utils import timezone
from django.views.generic import DetailView, ListView

from apps.cuentas.backends import reactivar_suspensiones_vencidas
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
        hoy = timezone.localdate()
        reactivar_suspensiones_vencidas()
        clientes = UsuarioPersonalizado.objects.filter(
            rol=RolUsuario.CLIENTE
        ).annotate(
            devoluciones_tardias=Count(
                'solicitudes_alquiler',
                filter=Q(
                    solicitudes_alquiler__politica_mora_aplica=True,
                    solicitudes_alquiler__dias_atraso__gt=0,
                ),
                distinct=True,
            ),
            alquileres_vencidos=Count(
                'solicitudes_alquiler',
                filter=Q(
                    solicitudes_alquiler__politica_mora_aplica=True,
                    solicitudes_alquiler__fecha_salida__isnull=False,
                    solicitudes_alquiler__fecha_retorno__isnull=True,
                    solicitudes_alquiler__fecha_fin__lt=hoy,
                ),
                distinct=True,
            ),
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
        context['infracciones_graves'] = context['solicitudes'].filter(
            politica_mora_aplica=True,
            dias_atraso__gt=3,
        ).count()
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
