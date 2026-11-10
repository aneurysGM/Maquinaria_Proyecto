from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.db.models import Q
from django.views.generic import CreateView,TemplateView
from apps.inventario.models import Unidad
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
        return reverse_lazy('cuentas:dashboard')


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

    def get(self, request, *args, **kwargs):
        if request.user.es_tecnico and not request.user.es_administrador:
            return redirect('tecnico_mantenimiento:dashboard')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
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
        elif not usuario.es_cliente:
            unidades = unidades.none()

        context['maquinarias_disponibles'] = unidades
        return context