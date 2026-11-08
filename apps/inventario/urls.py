from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    # Categorías
    path('categorias/', views.CategoriaListaView.as_view(), name='categoria_lista'),
    path('categorias/nuevo/', views.CategoriaCrearView.as_view(), name='categoria_crear'),
    
    # Maquinarias / Unidades
    path('maquinarias/', views.MaquinariaListaView.as_view(), name='maquinaria_lista'),
    path('maquinarias/nuevo/', views.MaquinariaCrearView.as_view(), name='maquinaria_crear'),
    
    # Ruta de Detalle de la Unidad
    path('maquinarias/detalle/<int:unidad_id>/', views.MaquinariaDetalleView.as_view(), name='maquinaria_detalle'),
    
    # Ruta para editar la unidad física y su maquinaria
    path('maquinarias/editar/<int:unidad_id>/', views.MaquinariaEditarView.as_view(), name='maquinaria_editar'),
    path('maquinarias/eliminar/<int:unidad_id>/', views.MaquinariaEliminarView.as_view(), name='maquinaria_eliminar'),
]