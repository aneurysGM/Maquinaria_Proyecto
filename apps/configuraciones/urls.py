from django.urls import path

from . import views


app_name = 'configuraciones'

urlpatterns = [
    path('', views.indice, name='indice'),
    path('mi-perfil/', views.MiPerfilView.as_view(), name='mi_perfil'),
    path('mi-perfil/correo/', views.CambiarCorreoView.as_view(), name='cambiar_correo'),
    path('mi-perfil/correo/confirmar/<str:token>/', views.ConfirmarCorreoView.as_view(), name='confirmar_correo'),
    path('contrasena/', views.CambiarContrasenaView.as_view(), name='cambiar_contrasena'),
]
