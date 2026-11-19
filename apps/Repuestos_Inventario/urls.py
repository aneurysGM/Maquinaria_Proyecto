from django.urls import path

from . import views


app_name = 'Repuestos_Inventario'

urlpatterns = [
    path('', views.repuestos_lista, name='lista'),
    path('nuevo/', views.repuesto_crear, name='crear'),
    path('guardar/', views.repuesto_guardar, name='guardar'),
    path('<int:repuesto_id>/entrada/', views.repuesto_entrada, name='entrada'),
]
