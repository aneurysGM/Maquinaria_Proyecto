from django.core.management.base import BaseCommand

from apps.alquileres.reservas import expirar_solicitudes_vencidas


class Command(BaseCommand):
    help = (
        'Marca como vencidas las solicitudes aprobadas sin pago inicial completo '
        'al cumplirse el plazo de cinco días y libera sus unidades.'
    )

    def handle(self, *args, **options):
        cantidad = expirar_solicitudes_vencidas()
        self.stdout.write(
            self.style.SUCCESS(
                f'Solicitudes vencidas y unidades liberadas: {cantidad}.'
            )
        )
