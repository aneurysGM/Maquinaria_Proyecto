from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.views.decorators.http import require_POST

from apps.reportes.exportacion_excel import CONTENT_TYPE
from .servicios import cerrar_periodo


@login_required(login_url='cuentas:login')
@require_POST
def cerrar_mes(request):
    if not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden cerrar el periodo.')

    resultado = cerrar_periodo()
    respuesta = HttpResponse(resultado.contenido, content_type=CONTENT_TYPE)
    respuesta['Content-Disposition'] = (
        f'attachment; filename="{resultado.nombre_archivo}"'
    )
    respuesta['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    respuesta['Pragma'] = 'no-cache'
    return respuesta
