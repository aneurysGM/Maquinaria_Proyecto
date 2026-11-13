from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View

from .forms import CambioContrasenaForm


def usuario_configurable(usuario):
    return (
        usuario.is_authenticated
        and usuario.is_active
        and (usuario.es_administrador or usuario.es_cliente or usuario.es_tecnico)
    )


class ConfiguracionesRequiredMixin(LoginRequiredMixin):
    login_url = 'cuentas:login'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not usuario_configurable(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class IndiceConfiguracionesView(ConfiguracionesRequiredMixin, View):
    def get(self, request):
        return render(request, 'configuraciones/indice.html')


class CambiarContrasenaView(ConfiguracionesRequiredMixin, PasswordChangeView):
    template_name = 'configuraciones/cambiar_contrasena.html'
    form_class = CambioContrasenaForm
    success_url = reverse_lazy('configuraciones:indice')

    def get_success_url(self):
        if self.request.user.primer_inicio_sesion:
            return reverse_lazy('tecnico_mantenimiento:dashboard')
        return super().get_success_url()

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        usuario = self.request.user
        if usuario.primer_inicio_sesion:
            usuario.primer_inicio_sesion = False
            usuario.save(update_fields=['primer_inicio_sesion'])
        messages.success(self.request, 'Tu contraseña se cambió correctamente.')
        return respuesta


indice = IndiceConfiguracionesView.as_view()
