from django.shortcuts import redirect
from django.urls import reverse


class PrimerInicioSesionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.url_cambio_contrasena = reverse('configuraciones:cambiar_contrasena')
        self.url_cerrar_sesion = reverse('cuentas:logout')

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        usuario = request.user
        if (
            usuario.is_authenticated
            and usuario.primer_inicio_sesion
            and request.path_info not in {
                self.url_cambio_contrasena,
                self.url_cerrar_sesion,
            }
        ):
            return redirect(self.url_cambio_contrasena)
        return None
