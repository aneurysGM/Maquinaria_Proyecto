from django.urls import path
from . import views

app_name = 'mantenimiento'

urlpatterns = [
    path('', views.mantenimiento_lista, name='mantenimiento_lista'),
    path('registrar/', views.mantenimiento_registrar, name='mantenimiento_registrar'),
    path('historial/<int:unidad_id>/', views.mantenimiento_historial, name='mantenimiento_historial'),
    path('finalizar/<int:unidad_id>/', views.mantenimiento_finalizar, name='mantenimiento_finalizar'),
]