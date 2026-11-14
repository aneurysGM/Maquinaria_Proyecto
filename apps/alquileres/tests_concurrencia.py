from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages, ERROR
from django.db import close_old_connections, connections, connection, DatabaseError
from django.test import RequestFactory, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from apps.ventas.views import pago_registrar, datos_revision
from django.core import signing
from .reservas import solicitudes_afectadas
from .models import SolicitudAlquiler
from .tests_datos import DatosIntegracion
from . import views


class OperacionesSimultaneasTests(DatosIntegracion, TransactionTestCase):
    def setUp(self):
        self.crear_datos()

    def ejecutar_simultaneas(self, operaciones):
        barrera = Barrier(len(operaciones))

        def ejecutar(operacion):
            close_old_connections()
            vista, usuario, identificador, datos = operacion
            request = RequestFactory().post('/operacion-de-prueba/', datos)
            request.user = usuario
            request.session = {}
            request._messages = FallbackStorage(request)
            try:
                barrera.wait(timeout=10)
                return vista(request, identificador).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(operaciones)) as ejecutor:
            return list(ejecutor.map(ejecutar, operaciones))

    def test_dos_aprobaciones_no_confirman_ni_rechazan_ninguna_reserva(self):
        a = self.crear_solicitud()
        b = self.crear_solicitud(cliente=self.otro)
        resultados = self.ejecutar_simultaneas([
            (views.solicitud_resolver, self.admin, a.pk, {'decision': 'Aprobada'}),
            (views.solicitud_resolver, self.admin, b.pk, {'decision': 'Aprobada'}),
        ])
        self.assertEqual(resultados, [302, 302])
        self.assertGreaterEqual(SolicitudAlquiler.objects.filter(estado='Aprobada').count(), 1)
        self.assertEqual(SolicitudAlquiler.objects.filter(estado='Rechazada').count(), 0)
        self.assertFalse(SolicitudAlquiler.objects.filter(fecha_confirmacion__isnull=False).exists())
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')

    def test_dos_confirmaciones_simultaneas_solo_reservan_una(self):
        a = self.crear_solicitud(estado='Aprobada')
        b = self.crear_solicitud(estado='Aprobada', cliente=self.otro)
        operaciones = []
        for solicitud, rival in [(a, b), (b, a)]:
            PagoAlquiler.objects.create(presupuesto=solicitud.presupuesto, concepto='renta', monto=750,
                                        metodo='efectivo', registrado_por=self.admin)
            firma = signing.dumps(datos_revision(solicitud, list(solicitudes_afectadas(solicitud))), salt='confirmar-reserva')
            operaciones.append((pago_registrar, self.admin, solicitud.presupuesto.pk, {
                'concepto': 'deposito', 'monto': '3000', 'metodo': 'efectivo',
                'revision_reserva': firma, f'motivo_{rival.pk}': 'Reservada por el otro cliente',
            }))
        resultados = self.ejecutar_simultaneas(operaciones)
        self.assertTrue(all(estado in (200, 302) for estado in resultados))
        self.assertEqual(SolicitudAlquiler.objects.filter(fecha_confirmacion__isnull=False).count(), 1)
        self.assertEqual(SolicitudAlquiler.objects.filter(estado='Rechazada').count(), 1)
        self.assertEqual(PagoAlquiler.objects.filter(concepto='deposito').count(), 1)
        rechazada = SolicitudAlquiler.objects.get(estado='Rechazada')
        self.assertEqual(rechazada.motivo_rechazo, 'Reservada por el otro cliente')

    def test_fallo_al_confirmar_pago_no_guarda_ni_publica_exito(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        PagoAlquiler.objects.create(presupuesto=solicitud.presupuesto, concepto='renta', monto=750,
                                    metodo='efectivo', registrado_por=self.admin)
        firma = signing.dumps(datos_revision(solicitud, []), salt='confirmar-reserva')
        self.client.force_login(self.admin)
        with patch.object(connection, '_commit', side_effect=DatabaseError('Fallo al confirmar')):
            respuesta = self.client.post(reverse('ventas:pago_registrar', args=[solicitud.presupuesto.pk]), {
                'concepto': 'deposito', 'monto': '3000', 'metodo': 'efectivo', 'revision_reserva': firma,
            })
        self.assertEqual([m.level for m in get_messages(respuesta.wsgi_request)], [ERROR])
        solicitud.refresh_from_db()
        self.assertIsNone(solicitud.fecha_confirmacion)
        self.assertEqual(PagoAlquiler.objects.count(), 1)

    def test_dos_solicitudes_duplicadas_solo_crean_un_presupuesto(self):
        datos = {'fecha_inicio': timezone.localdate().isoformat(), 'plan': 'diario', 'cantidad': 1}
        resultados = self.ejecutar_simultaneas([
            (views.solicitud_registrar, self.cliente, self.unidad.pk, datos),
            (views.solicitud_registrar, self.cliente, self.unidad.pk, datos),
        ])
        self.assertTrue(all(estado in (200, 302) for estado in resultados))
        self.assertIn(302, resultados)
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)
        self.assertEqual(PresupuestoAlquiler.objects.count(), 1)

    def test_dos_salidas_no_duplican_el_movimiento(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        self.completar_pago_inicial(solicitud)
        resultados = self.ejecutar_simultaneas([
            (views.solicitud_registrar_salida, self.admin, solicitud.pk, {}),
            (views.solicitud_registrar_salida, self.superadmin, solicitud.pk, {}),
        ])
        self.assertEqual(resultados, [302, 302])
        solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertIsNotNone(solicitud.fecha_salida)
        self.assertIn(solicitud.entregado_por_id, [self.admin.pk, self.superadmin.pk])
        self.assertEqual(self.unidad.estado, 'Alquilado')

    def test_dos_retornos_no_reescriben_el_horometro(self):
        solicitud = self.crear_entrega(atraso=4)
        resultados = self.ejecutar_simultaneas([
            (views.solicitud_registrar_retorno, self.admin, solicitud.pk, {'horas_uso_actualizadas': '12'}),
            (views.solicitud_registrar_retorno, self.superadmin, solicitud.pk, {'horas_uso_actualizadas': '15'}),
        ])
        self.assertEqual(resultados, [302, 302])
        solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        esperado = 12 if solicitud.recibido_por_id == self.admin.pk else 15
        self.assertEqual(self.unidad.horas_uso, esperado)
        self.assertEqual(solicitud.presupuesto.mora_total, 375)
