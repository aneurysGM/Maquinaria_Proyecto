from django.urls import path

from . import views


app_name = 'ventas'

urlpatterns = [
    path('', views.PresupuestoListaView.as_view(), name='presupuesto_lista'),
    path(
        'presupuestos/<int:presupuesto_id>/',
        views.PresupuestoDetalleView.as_view(),
        name='presupuesto_detalle',
    ),
    path(
        'presupuestos/<int:presupuesto_id>/pagos/',
        views.pago_registrar,
        name='pago_registrar',
    ),
    path(
        'presupuestos/<int:presupuesto_id>/reembolsos/',
        views.reembolso_registrar,
        name='reembolso_registrar',
    ),
]
