"""Modelos existentes que alimentan los reportes; aquí no se definen tablas."""

from apps.alquileres.models import SolicitudAlquiler
from apps.inventario.models import Unidad
from apps.mantenimiento.models import Mantenimiento

__all__ = ['Mantenimiento', 'SolicitudAlquiler', 'Unidad']
