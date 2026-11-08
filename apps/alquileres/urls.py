from django.urls import path
from . import views

app_name = 'alquileres'

urlpatterns = [
    path('solicitar/<int:unidad_id>/', views.solicitud_registrar, name='solicitud_registrar'),
    path('solicitudes/', views.solicitud_lista, name='solicitud_lista'),
    path('solicitudes/resolver/<int:solicitud_id>/', views.solicitud_resolver, name='solicitud_resolver'),
]