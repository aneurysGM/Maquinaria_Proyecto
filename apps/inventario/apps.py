from django.apps import AppConfig
from django.db.models.signals import post_migrate

def poblar_categorias_por_defecto(sender, **kwargs):
    """Crea categorías básicas automáticamente al migrar la base de datos."""
    # Importamos el modelo aquí adentro para evitar errores de carga circular
    from .models import Categoria
    
    categorias_iniciales = [
        {'nombre': 'Excavadoras', 'descripcion': 'Equipos de excavación y movimiento de tierra.'},
        {'nombre': 'Grúas', 'descripcion': 'Equipos de elevación y carga pesada para alturas.'},
        {'nombre': 'Montacargas', 'descripcion': 'Vehículos industriales para transporte de tarimas.'},
        {'nombre': 'Aplanadoras', 'descripcion': 'Maquinaria pesada para compactación de suelos.'},
        {'nombre': 'Retroexcavadoras', 'descripcion': 'Maquinaria versátil con cuchara y brazo excavador.'},
        {'nombre': 'Volquetas', 'descripcion': 'Camiones de volteo para transporte de materiales.'}
    ]
    
    # get_or_create verifica si existe, si no, la crea. Así no se duplican si migras 2 veces.
    for cat_data in categorias_iniciales:
        Categoria.objects.get_or_create(
            nombre=cat_data['nombre'], 
            defaults={'descripcion': cat_data['descripcion']}
        )


class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventario'

    def ready(self):
        # Conecta la señal para que se ejecute justo después de hacer un 'migrate'
        post_migrate.connect(poblar_categorias_por_defecto, sender=self)