from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from apps.cuentas.models import DireccionCliente, UsuarioPersonalizado, puede_editar_su_perfil
from .forms import CambioContrasenaForm, CambioCorreoForm, DireccionClienteForm, MiPerfilForm


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


class DireccionesClienteRequiredMixin(ConfiguracionesRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            not request.user.es_cliente or request.user.es_administrador
        ):
            raise PermissionDenied('Solo el Cliente puede administrar sus propias direcciones.')
        return super().dispatch(request, *args, **kwargs)


class MisDireccionesView(DireccionesClienteRequiredMixin, View):
    def get(self, request):
        return render(request, 'configuraciones/direccion_lista.html', {
            'direcciones': DireccionCliente.objects.filter(cliente=request.user),
        })


class DireccionFormView(DireccionesClienteRequiredMixin, View):
    def direccion_propia(self, request, direccion_id, *, bloquear=False):
        if direccion_id is None:
            return DireccionCliente(cliente=request.user)
        direcciones = DireccionCliente.objects.filter(cliente=request.user)
        if bloquear:
            direcciones = direcciones.select_for_update()
        return get_object_or_404(direcciones, pk=direccion_id)

    def get(self, request, direccion_id=None):
        direccion = self.direccion_propia(request, direccion_id)
        return render(request, 'configuraciones/direccion_form.html', {
            'form': DireccionClienteForm(instance=direccion), 'direccion': direccion,
        })

    @transaction.atomic
    def post(self, request, direccion_id=None):
        direccion = self.direccion_propia(request, direccion_id, bloquear=True)
        form = DireccionClienteForm(request.POST, instance=direccion)
        if form.is_valid():
            form.save()
            messages.success(request, 'La dirección se guardó correctamente.')
            return redirect('configuraciones:mis_direcciones')
        return render(request, 'configuraciones/direccion_form.html', {
            'form': form, 'direccion': direccion,
        })


class DireccionEliminarView(DireccionesClienteRequiredMixin, View):
    def get(self, request, direccion_id):
        direccion = get_object_or_404(DireccionCliente, pk=direccion_id, cliente=request.user)
        return render(request, 'configuraciones/direccion_confirmar_eliminar.html', {'direccion': direccion})

    @transaction.atomic
    def post(self, request, direccion_id):
        direccion = get_object_or_404(
            DireccionCliente.objects.select_for_update(), pk=direccion_id, cliente=request.user,
        )
        direccion.delete()
        messages.success(request, 'La dirección se eliminó. Las direcciones de alquileres confirmados se conservan.')
        return redirect('configuraciones:mis_direcciones')


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
        # Valida la contraseña y modifica únicamente la cuenta de la sesión.
        try:
            with transaction.atomic():
                usuario = UsuarioPersonalizado.objects.select_for_update().get(pk=request.user.pk)
                form = CambioCorreoForm(request.POST, usuario=usuario)
                if not puede_editar_su_perfil(usuario):
                    form.add_error(None, 'Tu cuenta no tiene permiso para cambiar el correo.')
                    return self.mostrar(request, form, status=403)
                if not form.is_valid():
                    return self.mostrar(request, form)
                usuario.email = form.cleaned_data['correo_nuevo']
                usuario.save(update_fields=['email'])
        except IntegrityError:
            form.add_error('correo_nuevo', 'Ese correo ya está registrado.')
        else:
            messages.success(request, 'Tu correo se actualizó correctamente. Ya puedes iniciar sesión con el correo nuevo y la misma contraseña.')
            return redirect('configuraciones:mi_perfil')
        return self.mostrar(request, form)


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
