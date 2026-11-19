from django.urls import path

from . import views


app_name = 'ordenes_trabajo'

urlpatterns = [
    path('', views.orden_lista, name='lista'),
    path('<int:mantenimiento_id>/', views.orden_detalle, name='detalle'),
    path('<int:mantenimiento_id>/actualizar/', views.orden_actualizar, name='actualizar'),
    path('<int:mantenimiento_id>/comentar/', views.orden_comentar, name='comentar'),
    path('<int:mantenimiento_id>/checklist/', views.orden_guardar_checklist, name='checklist'),
    path('<int:mantenimiento_id>/finalizar/', views.orden_finalizar, name='finalizar'),
    path('<int:mantenimiento_id>/repuestos/solicitar/', views.orden_solicitar_repuestos, name='solicitar_repuestos'),
    path('<int:mantenimiento_id>/repuestos/consumir/', views.orden_registrar_consumo, name='consumir_repuesto'),
    path('solicitudes-repuestos/<int:solicitud_id>/<str:accion>/', views.solicitud_repuesto_resolver, name='resolver_solicitud_repuesto'),
    path('repuestos/', views.repuesto_lista, name='repuestos'),
    path('repuestos/nuevo/', views.repuesto_crear, name='repuesto_crear'),
    path('repuestos/guardar/', views.repuesto_guardar, name='repuesto_guardar'),
    path('repuestos/<int:repuesto_id>/entrada/', views.repuesto_entrada, name='repuesto_entrada'),
]
