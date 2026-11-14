from .models import Mantenimiento


def mantenimientos_abiertos():
    """La fecha existente puede corresponder a un trabajo actual o futuro."""
    return Mantenimiento.objects.filter(fecha_fin__isnull=True).select_related(
        'unidad__maquinaria', 'tecnico',
    ).order_by('fecha', 'pk')
