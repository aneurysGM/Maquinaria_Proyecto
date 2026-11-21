from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler, ReembolsoDeposito, ReembolsoRenta
from .models import SolicitudAlquiler


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class MantenimientoForzadoTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-forzado@example.com', password='pass', rol=RolUsuario.ADMINISTRADOR,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-forzado@example.com', password='pass', rol=RolUsuario.TECNICO,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-forzado@example.com', password='pass', rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Equipos forzados')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='FOR-01', nombre='Equipo forzado',
            costo_adquisicion=1000, tarifa_diaria=100,
            tarifa_semanal=500, tarifa_mensual=1500,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria, numero_serie='FOR-01', estado='Alquilado',
        )
        hoy = timezone.localdate()
        self.solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente, unidad=self.unidad, estado='Aprobada',
            fecha_inicio=hoy + timedelta(days=2), fecha_fin=hoy + timedelta(days=4),
            fecha_revision=timezone.now(), revisado_por=self.admin,
        )
        self.presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=self.solicitud, tarifa_periodo=100, importe_renta=100,
            deposito_garantia=100,
        )
        for concepto, monto in [('renta', '30.00'), ('deposito', '20.00')]:
            PagoAlquiler.objects.create(
                presupuesto=self.presupuesto, concepto=concepto, monto=Decimal(monto),
                metodo='efectivo', registrado_por=self.admin,
            )
        self.datos = {
            'unidad': self.unidad.pk, 'fecha': hoy.isoformat(), 'tipo': 'Correctivo',
            'descripcion': 'Falla imprevista', 'costo': '0',
            'tecnico_responsable': self.tecnico.pk,
        }

    def test_confirmacion_cancelacion_y_reembolsos(self):
        self.client.force_login(self.admin)
        url = reverse('mantenimiento:mantenimiento_registrar')
        respuesta = self.client.post(url, self.datos)
        self.assertContains(respuesta, 'Confirma el mantenimiento forzado')
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'Aprobada')
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(url, {**self.datos, 'forzar': 'on'})
        self.assertEqual(respuesta.status_code, 302)
        self.solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'Cancelada')
        self.assertTrue(self.solicitud.cancelada_por_mantenimiento)
        self.assertEqual(self.unidad.estado, 'Mantenimiento')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('pendientes de devolución', mail.outbox[0].body)
        self.assertEqual(self.presupuesto.renta_por_reembolsar, Decimal('30.00'))
        self.assertEqual(self.presupuesto.deposito_por_reembolsar, Decimal('20.00'))
        self.assertFalse(ReembolsoRenta.objects.exists())
        self.assertFalse(ReembolsoDeposito.objects.exists())
        self.client.force_login(self.cliente)
        respuesta = self.client.get(reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk]))
        self.assertContains(respuesta, 'Renta pendiente de devolución')
        self.assertEqual(self.client.post(reverse('ventas:reembolso_renta_registrar', args=[self.presupuesto.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(reverse('ventas:reembolso_renta_registrar', args=[self.presupuesto.pk]), {
            'renta-monto': '31', 'renta-metodo': 'efectivo',
        })
        self.assertFalse(ReembolsoRenta.objects.exists())
        self.client.post(reverse('ventas:reembolso_renta_registrar', args=[self.presupuesto.pk]), {
            'renta-monto': '30', 'renta-metodo': 'efectivo',
        })
        self.client.post(reverse('ventas:reembolso_registrar', args=[self.presupuesto.pk]), {
            'monto': '20', 'metodo': 'efectivo',
        })
        self.assertEqual(self.presupuesto.renta_por_reembolsar, 0)
        self.assertEqual(self.presupuesto.deposito_por_reembolsar, 0)

    def test_tecnico_no_puede_forzar_unidad_entregada(self):
        self.solicitud.fecha_salida = timezone.now()
        self.solicitud.entregado_por = self.admin
        self.solicitud.save(update_fields=['fecha_salida', 'entregado_por'])
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(reverse('mantenimiento:mantenimiento_registrar'), {
            **self.datos, 'forzar': 'on',
        })
        self.assertContains(respuesta, 'debe retornar antes del mantenimiento')
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'Aprobada')

    def test_tecnico_cancela_todas_las_reservas_vigentes_sin_entregar(self):
        segunda = SolicitudAlquiler.objects.create(
            cliente=self.cliente, unidad=self.unidad, estado='Aprobada',
            fecha_inicio=timezone.localdate() + timedelta(days=30),
            fecha_fin=timezone.localdate() + timedelta(days=31),
        )
        pendiente = SolicitudAlquiler.objects.create(
            cliente=self.cliente, unidad=self.unidad, estado='Pendiente',
            fecha_inicio=timezone.localdate() + timedelta(days=30),
            fecha_fin=timezone.localdate() + timedelta(days=31),
        )
        anterior = SolicitudAlquiler.objects.create(
            cliente=self.cliente, unidad=self.unidad, estado='Aprobada',
            fecha_inicio=timezone.localdate() - timedelta(days=3),
            fecha_fin=timezone.localdate() - timedelta(days=1),
        )
        self.client.force_login(self.tecnico)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse('mantenimiento:mantenimiento_registrar'), {
                **self.datos, 'forzar': 'on',
            })
        self.assertEqual(respuesta.status_code, 302)
        for reserva in (self.solicitud, segunda):
            reserva.refresh_from_db()
            self.assertEqual(reserva.estado, 'Cancelada')
        pendiente.refresh_from_db()
        anterior.refresh_from_db()
        self.assertEqual(pendiente.estado, 'Pendiente')
        self.assertEqual(anterior.estado, 'Aprobada')
        self.assertEqual(len(mail.outbox), 2)

    def test_reembolso_no_permitido_para_cancelacion_ordinaria(self):
        self.solicitud.estado = 'Cancelada'
        self.solicitud.save(update_fields=['estado'])
        self.client.force_login(self.admin)
        self.client.post(reverse('ventas:reembolso_renta_registrar', args=[self.presupuesto.pk]), {
            'renta-monto': '30', 'renta-metodo': 'efectivo',
        })
        self.client.post(reverse('ventas:reembolso_registrar', args=[self.presupuesto.pk]), {
            'monto': '20', 'metodo': 'efectivo',
        })
        self.assertFalse(ReembolsoRenta.objects.exists())
        self.assertFalse(ReembolsoDeposito.objects.exists())


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

    def test_retorno_tardio_no_inactiva_al_cliente(self):
        hoy = timezone.localdate()
        self.crear_solicitud(
            estado='Aprobada',
            fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy - timedelta(days=25),
            fecha_salida=timezone.now() - timedelta(days=30),
            entregado_por=self.administrador,
            fecha_retorno=timezone.now() - timedelta(days=20),
            recibido_por=self.administrador,
            dias_atraso=5,
        )
        solicitud = self.crear_solicitud(
            estado='Aprobada',
            fecha_inicio=hoy - timedelta(days=10),
            fecha_fin=hoy - timedelta(days=6),
            fecha_salida=timezone.now() - timedelta(days=10),
            entregado_por=self.administrador,
            fecha_confirmacion=timezone.now() - timedelta(days=11),
        )
        self.unidad.estado = 'Alquilado'
        self.unidad.save(update_fields=['estado'])
        self.client.force_login(self.administrador)

        respuesta = self.client.post(
            reverse('alquileres:solicitud_retorno', args=[solicitud.pk]),
            {'horas_uso_actualizadas': '5.0', 'observaciones_retorno': ''},
        )

        self.assertRedirects(respuesta, reverse('alquileres:solicitud_lista'))
        solicitud.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertGreater(solicitud.dias_atraso, 3)
        self.assertTrue(self.cliente.is_active)
