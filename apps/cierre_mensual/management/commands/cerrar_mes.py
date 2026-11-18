from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.cierre_mensual.models import CierreMensual
from apps.cierre_mensual.servicios import cerrar_periodo


class Command(BaseCommand):
    help = 'Cierra el periodo de ingresos y guarda su Excel en el servidor.'

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        inicio_mes_siguiente = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)
        ultimo_dia = inicio_mes_siguiente - timedelta(days=1)
        if hoy != ultimo_dia:
            raise CommandError('Este comando solo se ejecuta el último día del mes.')

        if CierreMensual.objects.filter(
            origen='automatico',
            cerrado_en__date=hoy,
        ).exists():
            self.stdout.write('El cierre automático de hoy ya fue realizado.')
            return

        try:
            resultado = cerrar_periodo(
                origen='automatico',
                guardar_en_servidor=True,
            )
        except CierreMensual.DoesNotExist as error:
            raise CommandError('No existe un periodo de ingresos abierto.') from error

        self.stdout.write(self.style.SUCCESS(
            f'Cierre realizado: {resultado.cantidad_pagos} pagos, '
            f'RD${resultado.total:.2f}. Archivo: {resultado.archivo_servidor}'
        ))
