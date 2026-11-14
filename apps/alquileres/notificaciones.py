import logging
import smtplib

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail


logger = logging.getLogger(__name__)


def _enviar_correo(request, destinatario, asunto, contenido):
    if not destinatario:
        logger.error('No se pudo enviar el aviso de alquiler: el cliente no tiene correo.')
        if request is not None:
            messages.error(
                request,
                'El aviso quedó guardado en Mis alquileres, pero el cliente no tiene un correo registrado.',
            )
        return

    try:
        enviados = send_mail(
            asunto,
            contenido,
            settings.DEFAULT_FROM_EMAIL,
            [destinatario],
            fail_silently=False,
        )
    except (ImproperlyConfigured, OSError, smtplib.SMTPException):
        logger.exception('No se pudo enviar un aviso de alquiler a %s.', destinatario)
        if request is not None:
            messages.error(
                request,
                f'El aviso quedó guardado en Mis alquileres, pero no se pudo enviar el correo a {destinatario}.',
            )
        return

    if enviados != 1:
        logger.error('El backend de correo no aceptó el aviso para %s.', destinatario)
        if request is not None:
            messages.error(
                request,
                f'El aviso quedó guardado en Mis alquileres, pero el correo a {destinatario} no fue aceptado.',
            )


def notificar_indisponibilidad(solicitud, motivo, *, request=None):
    cliente = solicitud.cliente
    maquinaria = solicitud.unidad.maquinaria
    nombre = cliente.get_full_name().strip() or cliente.email
    asunto = f'Actualización de tu solicitud de alquiler #{solicitud.pk}'
    contenido = (
        f'Hola {nombre},\n\n'
        f'No podremos atender tu solicitud de {maquinaria.nombre} '
        f'entre el {solicitud.fecha_inicio:%d/%m/%Y} y el {solicitud.fecha_fin:%d/%m/%Y}.\n\n'
        f'Motivo: {motivo}\n\n'
        'En Mis alquileres puedes aceptar el aplazamiento hasta que la maquinaria '
        'esté disponible o cancelar la solicitud. Si la aplazas, te avisaremos '
        'cuando se programe la nueva fecha y deberás completar el pago antes del inicio.\n\n'
        'Saludos cordiales,\nEquipo de alquileres'
    )
    _enviar_correo(request, cliente.email, asunto, contenido)


def notificar_reprogramacion(solicitud, *, request=None):
    cliente = solicitud.cliente
    nombre = cliente.get_full_name().strip() or cliente.email
    asunto = f'Nueva fecha para tu solicitud de alquiler #{solicitud.pk}'
    contenido = (
        f'Hola {nombre},\n\n'
        f'La maquinaria {solicitud.unidad.maquinaria.nombre} estará disponible para tu alquiler '
        f'del {solicitud.fecha_inicio:%d/%m/%Y} al {solicitud.fecha_fin:%d/%m/%Y}.\n'
        f'Completa el pago inicial antes del {solicitud.fecha_limite_pago:%d/%m/%Y %H:%M}; '
        'debe estar pagado antes de la fecha de inicio.\n\n'
        'Saludos cordiales,\nEquipo de alquileres'
    )
    _enviar_correo(request, cliente.email, asunto, contenido)
