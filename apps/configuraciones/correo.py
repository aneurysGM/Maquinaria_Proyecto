import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import (
    SolicitudCambioCorreo, UsuarioPersonalizado, puede_editar_su_perfil,
)


class ErrorCambioCorreo(ValueError):
    pass


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def solicitar_cambio_correo(request, usuario, correo):
    """El llamador mantiene bloqueado el usuario y valida su contraseña."""
    if not puede_editar_su_perfil(usuario):
        raise ErrorCambioCorreo('Tu cuenta no tiene permiso para cambiar el correo.')
    if UsuarioPersonalizado.objects.filter(email__iexact=correo).exists():
        raise ErrorCambioCorreo('Ese correo ya está registrado.')

    token = secrets.token_urlsafe(32)
    solicitud = SolicitudCambioCorreo.objects.create(
        usuario=usuario, correo_anterior=usuario.email, correo_nuevo=correo,
        token_hash=hash_token(token),
        vence_en=timezone.now() + timedelta(seconds=settings.CAMBIO_CORREO_VIGENCIA_SEGUNDOS),
    )
    ruta = reverse('configuraciones:confirmar_correo', args=[token])
    enlace = request.build_absolute_uri(ruta)
    texto = render_to_string('configuraciones/correo_confirmacion.txt', {
        'usuario': usuario, 'solicitud': solicitud, 'enlace': enlace,
    })
    enviados = send_mail(
        'Confirma tu nuevo correo · MaquiRent', texto,
        settings.DEFAULT_FROM_EMAIL, [correo], fail_silently=False,
    )
    if enviados != 1:
        raise ErrorCambioCorreo('No se pudo enviar el enlace. Inténtalo de nuevo más tarde.')
    # Solo se reemplaza el enlace anterior cuando el envío nuevo tuvo éxito.
    SolicitudCambioCorreo.objects.filter(
        usuario=usuario, usado_en__isnull=True, motivo_invalidacion='',
    ).exclude(pk=solicitud.pk).update(
        motivo_invalidacion='Este enlace fue reemplazado por una solicitud más reciente.',
    )
    return solicitud


def validar_solicitud(solicitud, usuario):
    if solicitud.usado_en:
        raise ErrorCambioCorreo('Este enlace ya se usó. El correo activo no se ha modificado.')
    if solicitud.motivo_invalidacion:
        raise ErrorCambioCorreo(solicitud.motivo_invalidacion)
    if timezone.now() >= solicitud.vence_en:
        raise ErrorCambioCorreo('Este enlace venció. Solicita un nuevo cambio de correo.')
    if not puede_editar_su_perfil(usuario):
        raise ErrorCambioCorreo('Tu cuenta ya no tiene permiso para cambiar el correo.')
    if usuario.email != solicitud.correo_anterior:
        raise ErrorCambioCorreo('El correo de la cuenta cambió. Solicita un enlace nuevo.')
    if UsuarioPersonalizado.objects.filter(email__iexact=solicitud.correo_nuevo).exists():
        raise ErrorCambioCorreo('Ese correo ya está registrado. Se conservó tu correo activo.')


def obtener_solicitud(token):
    solicitud = SolicitudCambioCorreo.objects.filter(token_hash=hash_token(token)).first()
    if solicitud is None:
        raise ErrorCambioCorreo('Este enlace de confirmación no es válido.')
    return solicitud


@transaction.atomic
def confirmar_cambio_correo(token, visitante):
    solicitud = obtener_solicitud(token)
    # Orden de bloqueos compartido por solicitud y perfil.
    usuario = UsuarioPersonalizado.objects.select_for_update().get(pk=solicitud.usuario_id)
    solicitud = SolicitudCambioCorreo.objects.select_for_update().get(pk=solicitud.pk)
    if visitante.is_authenticated and visitante.pk != usuario.pk:
        raise ErrorCambioCorreo('Este enlace pertenece a otra cuenta. Cierra esa sesión para continuar.')
    validar_solicitud(solicitud, usuario)
    try:
        with transaction.atomic():
            usuario.email = solicitud.correo_nuevo
            usuario.save(update_fields=['email'])
    except IntegrityError as error:
        raise ErrorCambioCorreo('Ese correo ya está registrado. Se conservó tu correo activo.') from error
    solicitud.usado_en = timezone.now()
    solicitud.save(update_fields=['usado_en'])
    return usuario
