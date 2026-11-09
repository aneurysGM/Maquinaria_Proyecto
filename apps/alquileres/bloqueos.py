"""Bloqueo común de la unidad para reservas, movimientos y edición."""
from django.db import connection
from django.db.models import F

from apps.inventario.models import Unidad


def bloquear_unidad(**filtros):
    """Debe llamarse dentro de transaction.atomic(), antes de leer disponibilidad.

    SQLite no ofrece SELECT FOR UPDATE. La actualización sin cambio adquiere
    su bloqueo de escritura antes de las lecturas y serializa las decisiones.
    En los demás motores se utiliza el bloqueo de fila de Django.
    """
    unidades = Unidad.objects.filter(**filtros)
    if connection.vendor == 'sqlite':
        unidades.update(estado=F('estado'))
    return unidades.select_for_update().select_related('maquinaria').get()
