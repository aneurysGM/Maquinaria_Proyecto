from django.urls import path

from . import views


app_name = 'configuraciones'

urlpatterns = [
    path('', views.indice, name='indice'),
    path('contrasena/', views.CambiarContrasenaView.as_view(), name='cambiar_contrasena'),
]
