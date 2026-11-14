from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from django.utils import timezone
from django.views.generic import CreateView,TemplateView
from apps.alquileres.models import SolicitudAlquiler
from apps.alquileres.reservas import reservas_confirmadas
from apps.inventario.models import Unidad
from apps.mantenimiento.consultas import mantenimientos_abiertos
from apps.ventas.consultas import presupuestos_con_pago_vencido
from apps.ventas.models import PagoAlquiler
from .forms import CorreoAuthenticationForm, RegistroClienteForm
from .models import UsuarioPersonalizado

class IniciarSesionView(LoginView):
    """
    Vista de inicio de sesión personalizada. 
    Como configuramos USERNAME_FIELD = 'email', Django autenticará automáticamente 
    usando el correo electrónico.
    """
    template_name = 'cuentas/login.html'
    authentication_form = CorreoAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        if self.request.user.is_authenticated and self.request.user.primer_inicio_sesion:
            return reverse_lazy('configuraciones:cambiar_contrasena')
        return self.get_redirect_url() or reverse_lazy('cuentas:dashboard')


class RegistrarClienteView(CreateView):
    """
    Vista encargada del registro público de nuevos clientes.
    """
    form_class = RegistroClienteForm
    template_name = 'cuentas/registro.html'
    success_url = reverse_lazy('cuentas:login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Evaluamos si la tabla de usuarios está completamente vacía
        context['es_primer_usuario'] = not UsuarioPersonalizado.objects.exists()
        return context

class DashboardAdminView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/admin_index.html'
    login_url = 'cuentas:login'

    def get_template_names(self):
        if self.request.user.es_cliente and not self.request.user.es_administrador:
            return ['dashboard/cliente_index.html']
        return super().get_template_names()

    def get(self, request, *args, **kwargs):
        if request.user.es_tecnico and not request.user.es_administrador:
            return redirect('tecnico_mantenimiento:dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        if usuario.es_cliente and not usuario.es_administrador:
            from apps.alquileres.views import solicitudes_consultables
            context['solicitudes'] = [s for s in solicitudes_consultables(usuario)
                                      if s.estado_cliente not in ('Rechazado', 'Vencido', 'Devuelto')]
            return context
        unidades = Unidad.objects.select_related(
            'maquinaria__categoria',
            'maquinaria__registrada_por',
        ).prefetch_related('maquinaria__imagenes').filter(
            activo=True,
            estado='Disponible',
            maquinaria__activo=True,
        )

        if usuario.es_administrador:
            unidades = unidades.filter(
                Q(maquinaria__registrada_por=usuario)
                | Q(maquinaria__registrada_por__isnull=True)
            )
            ahora = timezone.now()
            local = timezone.localtime(ahora, timezone.get_default_timezone())
            inicio_mes = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            siguiente_mes = (inicio_mes + timedelta(days=32)).replace(day=1)
            pendientes = SolicitudAlquiler.objects.filter(estado='Pendiente').select_related(
                'cliente', 'unidad__maquinaria',
            ).order_by('fecha_creacion', 'pk')
            mantenimientos = mantenimientos_abiertos()
            pagos_vencidos = presupuestos_con_pago_vencido(ahora=ahora)
            context['kpis'] = {
                'disponibles': unidades.count(),
                'solicitudes_pendientes': pendientes.count(),
                'alquileres_activos': reservas_confirmadas().count(),
                'en_mantenimiento': Unidad.objects.filter(estado='Mantenimiento').count(),
                'ingresos_mes': PagoAlquiler.objects.filter(
                    concepto__in=('renta', 'mora'), creado_en__gte=inicio_mes,
                    creado_en__lt=siguiente_mes,
                ).aggregate(total=Sum('monto', default=Decimal('0.00')))['total'],
            }
            context.update({
                'solicitudes_pendientes': pendientes[:5],
                'mantenimientos_atencion': mantenimientos[:5],
                'mantenimientos_atencion_total': mantenimientos.count(),
                'pagos_vencidos': pagos_vencidos[:5],
                'pagos_vencidos_total': len(pagos_vencidos),
                'hoy': local.date(),
            })
        elif not usuario.es_cliente:
            unidades = unidades.none()

        context['maquinarias_disponibles'] = unidades
        return context
