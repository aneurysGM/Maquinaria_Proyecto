from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from .models import SolicitudAlquiler


class AccionesClienteSolicitudTests(TestCase):
    def setUp(self):
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-solicitud@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.administrador = UsuarioPersonalizado.objects.create_user(
            email='admin-solicitud@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        categoria = Categoria.objects.create(nombre='Pruebas de solicitudes')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='SOL-01',
            nombre='Equipo para solicitudes',
            costo_adquisicion=Decimal('1000.00'),
            tarifa_diaria=Decimal('100.00'),
            tarifa_semanal=Decimal('500.00'),
            tarifa_mensual=Decimal('1500.00'),
            deposito_garantia=Decimal('100.00'),
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SOL-SERIE-01',
        )
        self.client.force_login(self.cliente)

    def crear_solicitud(self, **campos):
        hoy = timezone.localdate()
        valores = {
            'cliente': self.cliente,
            'unidad': self.unidad,
            'fecha_inicio': hoy + timedelta(days=2),
            'fecha_fin': hoy + timedelta(days=4),
        }
        valores.update(campos)
        return SolicitudAlquiler.objects.create(**valores)

    def responder(self, solicitud, **datos):
        return self.client.post(
            reverse(
                'alquileres:solicitud_responder_disponibilidad',
                args=[solicitud.pk],
            ),
            datos,
        )

    def test_cliente_elige_fecha_y_se_conserva_duracion_para_revision(self):
        solicitud = self.crear_solicitud(
            estado='Aprobada',
            revisado_por=self.administrador,
            fecha_revision=timezone.now() - timedelta(days=1),
            fecha_aviso_disponibilidad=timezone.now(),
            motivo_disponibilidad='La unidad no estará disponible.',
        )
        fecha_elegida = timezone.localdate() + timedelta(days=10)

        respuesta = self.responder(
            solicitud,
            accion='aplazar',
            fecha_inicio=fecha_elegida.isoformat(),
        )

        self.assertRedirects(respuesta, reverse('alquileres:solicitud_lista'))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.fecha_inicio, fecha_elegida)
        self.assertEqual(solicitud.fecha_fin, fecha_elegida + timedelta(days=2))
        self.assertEqual(solicitud.estado, 'Pendiente')
        self.assertIsNone(solicitud.fecha_revision)
        self.assertIsNone(solicitud.revisado_por)
        self.assertIsNone(solicitud.fecha_aviso_disponibilidad)
        self.assertEqual(solicitud.motivo_disponibilidad, '')
        self.assertFalse(solicitud.aplazada)

    def test_cliente_ve_el_selector_de_fecha_y_cancelacion_para_solicitud_impaga(self):
        solicitud = self.crear_solicitud(
            fecha_aviso_disponibilidad=timezone.now(),
            motivo_disponibilidad='La unidad no estará disponible.',
        )

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="fecha_inicio"')
        self.assertContains(respuesta, 'Solicitar nueva fecha')
        self.assertContains(respuesta, 'Cancelar solicitud')

    def test_aplazamiento_no_acepta_una_fecha_que_cruza_reserva_confirmada(self):
        fecha_elegida = timezone.localdate() + timedelta(days=10)
        solicitud = self.crear_solicitud(
            fecha_aviso_disponibilidad=timezone.now(),
            motivo_disponibilidad='La unidad no estará disponible.',
        )
        self.crear_solicitud(
            cliente=self.administrador,
            estado='Aprobada',
            fecha_inicio=fecha_elegida,
            fecha_fin=fecha_elegida + timedelta(days=1),
            fecha_confirmacion=timezone.now(),
        )

        respuesta = self.responder(
            solicitud,
            accion='aplazar',
            fecha_inicio=fecha_elegida.isoformat(),
        )

        self.assertRedirects(respuesta, reverse('alquileres:solicitud_lista'))
        solicitud.refresh_from_db()
        self.assertNotEqual(solicitud.fecha_inicio, fecha_elegida)
        self.assertIsNotNone(solicitud.fecha_aviso_disponibilidad)
        self.assertEqual(solicitud.estado, 'Pendiente')

    def test_cliente_puede_cancelar_solicitudes_impagas_en_distintos_estados(self):
        for estado in ('Pendiente', 'Aprobada', 'Rechazada', 'Vencida'):
            with self.subTest(estado=estado):
                solicitud = self.crear_solicitud(estado=estado)
                respuesta = self.responder(solicitud, accion='cancelar')

                self.assertRedirects(respuesta, reverse('alquileres:solicitud_lista'))
                solicitud.refresh_from_db()
                self.assertEqual(solicitud.estado, 'Cancelada')

    def test_cliente_no_puede_cancelar_solicitud_con_pago_registrado(self):
        solicitud = self.crear_solicitud()
        presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=solicitud,
            tarifa_periodo=Decimal('100.00'),
            importe_renta=Decimal('100.00'),
            deposito_garantia=Decimal('100.00'),
        )
        PagoAlquiler.objects.create(
            presupuesto=presupuesto,
            monto=Decimal('10.00'),
            concepto='renta',
            metodo='efectivo',
            registrado_por=self.administrador,
        )

        respuesta = self.responder(solicitud, accion='cancelar')

        self.assertRedirects(respuesta, reverse('alquileres:solicitud_lista'))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'Pendiente')
