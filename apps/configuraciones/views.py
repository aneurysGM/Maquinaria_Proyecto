import logging
from smtplib import SMTPException

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.cuentas.models import UsuarioPersonalizado, puede_editar_su_perfil
from .correo import (
    ErrorCambioCorreo, confirmar_cambio_correo, obtener_solicitud,
    solicitar_cambio_correo, validar_solicitud,
)
from .forms import CambioContrasenaForm, CambioCorreoForm, MiPerfilForm


logger = logging.getLogger(__name__)


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


@method_decorator(never_cache, name='dispatch')
class MiPerfilView(ConfiguracionesRequiredMixin, View):
    def mostrar(self, request, usuario, form=None, status=200):
        return render(request, 'configuraciones/mi_perfil.html', {
            'perfil': usuario,
            'form': form if form is not None else MiPerfilForm(instance=usuario),
        }, status=status)

    def get(self, request):
        return self.mostrar(request, request.user)

    @transaction.atomic
    def post(self, request):
        usuario = UsuarioPersonalizado.objects.select_for_update().get(pk=request.user.pk)
        if not puede_editar_su_perfil(usuario):
            messages.error(request, 'Tu cuenta no tiene permiso para editar el perfil.')
            return self.mostrar(request, usuario, status=403)
        form = MiPerfilForm(request.POST, instance=usuario)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.save(update_fields=['first_name', 'last_name', 'telefono'])
            messages.success(request, 'Tus datos personales se guardaron correctamente.')
            return redirect('configuraciones:mi_perfil')
        return self.mostrar(request, usuario, form)


@method_decorator(sensitive_post_parameters('contrasena_actual'), name='dispatch')
@method_decorator(never_cache, name='dispatch')
class CambiarCorreoView(ConfiguracionesRequiredMixin, View):
    def mostrar(self, request, form, status=200):
        return render(request, 'configuraciones/cambiar_correo.html', {'form': form}, status=status)

    def get(self, request):
        if not puede_editar_su_perfil(request.user):
            messages.error(request, 'Tu cuenta no tiene permiso para cambiar el correo.')
            return redirect('configuraciones:mi_perfil')
        return self.mostrar(request, CambioCorreoForm(usuario=request.user))

    def post(self, request):
        # Serializa los cambios de la misma cuenta durante la solicitud.
        try:
            with transaction.atomic():
                usuario = UsuarioPersonalizado.objects.select_for_update().get(pk=request.user.pk)
                form = CambioCorreoForm(request.POST, usuario=usuario)
                if not puede_editar_su_perfil(usuario):
                    form.add_error(None, 'Tu cuenta no tiene permiso para cambiar el correo.')
                    return self.mostrar(request, form, status=403)
                if not form.is_valid():
                    return self.mostrar(request, form)
                solicitar_cambio_correo(request, usuario, form.cleaned_data['correo_nuevo'])
        except ErrorCambioCorreo as error:
            form.add_error(None, str(error))
        except (SMTPException, OSError):
            logger.warning('No se pudo enviar la confirmación de cambio de correo.')
            form.add_error(None, 'No se pudo enviar el enlace. Revisa la configuración del envío con el administrador e inténtalo de nuevo.')
        else:
            messages.success(request, 'Enviamos un enlace al correo nuevo. Tu correo actual sigue activo hasta que confirmes el cambio.')
            return redirect('configuraciones:mi_perfil')
        return self.mostrar(request, form)


@method_decorator(never_cache, name='dispatch')
class ConfirmarCorreoView(View):
    def get(self, request, token):
        try:
            solicitud = obtener_solicitud(token)
            if request.user.is_authenticated and request.user.pk != solicitud.usuario_id:
                raise ErrorCambioCorreo('Este enlace pertenece a otra cuenta. Cierra esa sesión para continuar.')
            validar_solicitud(solicitud, solicitud.usuario)
        except ErrorCambioCorreo as error:
            return render(request, 'configuraciones/confirmar_correo.html', {'error': str(error)}, status=400)
        # Abrir el enlace no lo consume: evita confirmaciones por escáneres de correo.
        return render(request, 'configuraciones/confirmar_correo.html', {'solicitud': solicitud})

    def post(self, request, token):
        try:
            confirmar_cambio_correo(token, request.user)
        except ErrorCambioCorreo as error:
            return render(request, 'configuraciones/confirmar_correo.html', {'error': str(error)}, status=400)
        return render(request, 'configuraciones/confirmar_correo.html', {'confirmado': True})


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
