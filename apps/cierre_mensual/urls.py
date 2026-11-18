from django.urls import path

from . import views


app_name = 'cierre_mensual'

urlpatterns = [
    path('cerrar/', views.cerrar_mes, name='cerrar_mes'),
]
