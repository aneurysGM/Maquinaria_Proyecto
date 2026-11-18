from django.urls import path

from . import views


app_name = 'cierre_mensual'

urlpatterns = [
    path('', views.historial_mensual, name='historial'),
    path('<int:anio>/<int:mes>/', views.detalle_mes, name='mes'),
    path(
        '<int:anio>/<int:mes>/semana/<int:semana>/',
        views.detalle_semana,
        name='semana',
    ),
    path('cerrar/', views.cerrar_mes, name='cerrar_mes'),
]
