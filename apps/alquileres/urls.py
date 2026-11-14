from django.urls import path
from . import views

app_name = 'alquileres'

urlpatterns = [
    path('solicitar/<int:unidad_id>/', views.solicitud_registrar, name='solicitud_registrar'),
    path('solicitudes/', views.solicitud_lista, name='solicitud_lista'),
    path('solicitudes/sugerencias-codigos/', views.solicitud_codigos, name='solicitud_codigos'),
    path('solicitudes/<int:solicitud_id>/', views.solicitud_detalle, name='solicitud_detalle'),
    path('entregas/', views.entrega_lista, name='entrega_lista'),
    path('solicitudes/resolver/<int:solicitud_id>/', views.solicitud_resolver, name='solicitud_resolver'),
    path('solicitudes/<int:solicitud_id>/salida/', views.solicitud_registrar_salida, name='solicitud_salida'),
    path('solicitudes/<int:solicitud_id>/retorno/', views.solicitud_registrar_retorno, name='solicitud_retorno'),
]
