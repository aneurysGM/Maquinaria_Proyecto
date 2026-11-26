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


def notificar_vencimiento(solicitud, enlace, *, request=None):
    cliente = solicitud.cliente
    nombre = cliente.get_full_name().strip() or cliente.email
    asunto = f'Tu solicitud de alquiler vencida #{solicitud.pk}'
    contenido = (
        f'Hola {nombre},\n\n'
        f'El plazo de pago inicial de tu solicitud de {solicitud.unidad.maquinaria.nombre} '
        'terminó. Si todavía te interesa, puedes volver a solicitarla con nuevas fechas '
        'desde Mis alquileres. La disponibilidad se comprobará al enviar la nueva solicitud.\n\n'
        f'Mis alquileres: {enlace}\n\n'
        'Saludos cordiales,\nEquipo de alquileres'
    )
    _enviar_correo(request, cliente.email, asunto, contenido)


def notificar_cancelacion_mantenimiento(solicitud, *, request=None):
    cliente = solicitud.cliente
    nombre = cliente.get_full_name().strip() or cliente.email
    asunto = f'Cancelación de tu solicitud de alquiler #{solicitud.pk}'
    contenido = (
        f'Hola {nombre},\n\n'
        f'Tu solicitud de {solicitud.unidad.maquinaria.nombre} fue cancelada porque la unidad '
        'requiere mantenimiento forzado y aún no se ha entregado.\n'
        'Los importes pagados por renta y depósito quedan pendientes de devolución; '
        'contacta al administrador para coordinarla. Puedes consultar el estado en Mis alquileres.\n\n'
        'Puedes solicitar otra maquinaria o realizar una nueva solicitud cuando esta unidad '
        'esté disponible.\n\nSaludos cordiales,\nEquipo de alquileres'
    )
    _enviar_correo(request, cliente.email, asunto, contenido)
