from django.urls import path

from . import views


app_name = 'configuraciones'

urlpatterns = [
    path('', views.indice, name='indice'),
    path('mis-direcciones/', views.MisDireccionesView.as_view(), name='mis_direcciones'),
    path('mis-direcciones/nueva/', views.DireccionFormView.as_view(), name='direccion_agregar'),
    path('mis-direcciones/<int:direccion_id>/editar/', views.DireccionFormView.as_view(), name='direccion_editar'),
    path('mis-direcciones/<int:direccion_id>/eliminar/', views.DireccionEliminarView.as_view(), name='direccion_eliminar'),
    path('mi-perfil/', views.MiPerfilView.as_view(), name='mi_perfil'),
    path('mi-perfil/correo/', views.CambiarCorreoView.as_view(), name='cambiar_correo'),
    path('contrasena/', views.CambiarContrasenaView.as_view(), name='cambiar_contrasena'),
]
