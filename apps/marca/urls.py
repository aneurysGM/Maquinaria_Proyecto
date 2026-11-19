from django.urls import path

from . import views


app_name = 'marca'

urlpatterns = [
    path('', views.MarcaListaView.as_view(), name='marca_lista'),
    path('nueva/', views.MarcaCrearView.as_view(), name='marca_crear'),
    path('<int:marca_id>/editar/', views.MarcaEditarView.as_view(), name='marca_editar'),
    path('<int:marca_id>/eliminar/', views.MarcaEliminarView.as_view(), name='marca_eliminar'),
]
