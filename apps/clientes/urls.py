from django.urls import path

from . import views


app_name = 'clientes'

urlpatterns = [
    path('', views.ClienteListaView.as_view(), name='cliente_lista'),
    path('<int:pk>/', views.ClienteDetalleView.as_view(), name='cliente_detalle'),
]
