from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

<<<<<<< HEAD
from django.core import mail
from django.test import TestCase, override_settings
=======
from django.db import DatabaseError
from django.test import Client, TestCase
>>>>>>> 191d8e13641f7d9c3cc64f83dd23cd71f42e1ac5
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import DireccionCliente, RolUsuario, UsuarioPersonalizado
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


class DireccionEntregaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cliente = UsuarioPersonalizado.objects.create_user(email='direccion@example.com')
        cls.otro = UsuarioPersonalizado.objects.create_user(email='otra-direccion@example.com')
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-direccion@example.com', rol=RolUsuario.ADMINISTRADOR,
        )
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-direccion@example.com', rol=RolUsuario.TECNICO,
        )
        categoria = Categoria.objects.create(nombre='Direcciones')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='DIR-01', nombre='Excavadora',
            costo_adquisicion=1000, tarifa_diaria=100, tarifa_semanal=500,
            tarifa_mensual=1500, deposito_garantia=100,
        )
        cls.unidad = Unidad.objects.create(maquinaria=maquinaria, numero_serie='DIR-SERIE')

    def setUp(self):
        self.client.force_login(self.cliente)
        self.solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente, unidad=self.unidad, estado='Aprobada',
            fecha_inicio=timezone.localdate(), fecha_fin=timezone.localdate() + timedelta(days=1),
            fecha_revision=timezone.now(), revisado_por=self.admin,
        )
        self.presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=self.solicitud, tarifa_periodo=100, importe_renta=100, deposito_garantia=100,
        )
        self.url = reverse('alquileres:solicitud_direccion_entrega', args=[self.solicitud.pk])
        self.detalle = reverse('alquileres:solicitud_detalle', args=[self.solicitud.pk])
        self.nueva = {
            'tipo': 'nueva', 'direccion': 'Calle Principal 15, San Luis, Santo Domingo Este',
            'referencia': 'Frente al parque',
        }

    def pagar(self):
        # Recorre el flujo existente: renta, revisión firmada y depósito final.
        self.client.force_login(self.admin)
        url = reverse('ventas:pago_registrar', args=[self.presupuesto.pk])
        self.assertEqual(self.client.post(url, {
            'concepto': 'renta', 'monto': '100', 'metodo': 'efectivo',
        }).status_code, 302)
        presupuesto = self.client.get(reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk]))
        self.assertEqual(self.client.post(url, {
            'concepto': 'deposito', 'monto': '100', 'metodo': 'efectivo',
            'revision_reserva': presupuesto.context['revision_reserva'],
        }).status_code, 302)
        self.solicitud.refresh_from_db()
        self.assertIsNotNone(self.solicitud.fecha_confirmacion)
        self.client.force_login(self.cliente)

    def guardar_direccion(self, cliente=None, **datos):
        return DireccionCliente.objects.create(
            cliente=cliente or self.cliente, nombre=datos.get('nombre', 'Obra en San Luis'),
            direccion=datos.get('direccion', self.nueva['direccion']),
            referencia=datos.get('referencia', self.nueva['referencia']),
        )

    def test_pago_actual_habilita_direccion_en_detalle_lista_y_presupuesto(self):
        self.assertNotContains(self.client.get(self.detalle), 'Indicar dirección de entrega')
        self.pagar()
        self.assertEqual(self.solicitud.estado_cliente, 'Pendiente de dirección de entrega')
        for url in (self.detalle, reverse('alquileres:solicitud_lista'),
                    reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk])):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                self.assertContains(respuesta, 'Pendiente de dirección de entrega')
                self.assertContains(respuesta, 'Indicar dirección de entrega')

    def test_cliente_vuelve_en_otra_sesion_despues_de_pagar(self):
        self.pagar()
        self.client.logout()
        otro_navegador = Client()
        otro_navegador.force_login(self.cliente)
        self.assertContains(otro_navegador.get(self.detalle), 'Indicar dirección de entrega')
        self.assertEqual(otro_navegador.post(self.url, self.nueva).status_code, 302)
        self.solicitud.refresh_from_db()
        self.assertTrue(self.solicitud.direccion_entrega_confirmada)

    def test_sin_guardadas_abre_nueva_y_confirma_sin_guardar_en_libreta(self):
        self.pagar()
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context['form'].modo, 'nueva')
        self.assertContains(respuesta, 'name="direccion"')
        self.assertNotContains(respuesta, 'name="direccion_guardada"')
        self.assertRedirects(self.client.post(self.url, self.nueva), self.detalle)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.direccion_entrega, self.nueva['direccion'])
        self.assertEqual(self.solicitud.referencia_entrega, self.nueva['referencia'])
        self.assertIsNotNone(self.solicitud.fecha_direccion_confirmada)
        self.assertFalse(DireccionCliente.objects.exists())
        self.assertEqual(self.solicitud.estado_cliente, 'Pendiente de entrega')

    def test_nueva_se_guarda_con_nombre_solo_para_el_titular(self):
        self.pagar()
        self.client.post(self.url, {**self.nueva, 'guardar': 'on', 'nombre': ' Obra en San Luis ',
                                    'cliente': self.otro.pk})
        direccion = DireccionCliente.objects.get()
        self.assertEqual(direccion.cliente, self.cliente)
        self.assertEqual(direccion.nombre, 'Obra en San Luis')
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.nombre_direccion_entrega, direccion.nombre)

    def test_nueva_valida_blancos_longitudes_y_nombre_condicional(self):
        self.pagar()
        for datos, campo in (({'direccion': '   '}, 'direccion'),
                             ({'direccion': 'a' * 501}, 'direccion'),
                             ({'referencia': 'a' * 301}, 'referencia'),
                             ({'guardar': 'on', 'nombre': '   '}, 'nombre'),
                             ({'guardar': 'on', 'nombre': 'a' * 101}, 'nombre')):
            with self.subTest(campo=campo, datos=datos):
                respuesta = self.client.post(self.url, {**self.nueva, **datos})
                self.assertIn(campo, respuesta.context['form'].errors)
                self.solicitud.refresh_from_db()
                self.assertIsNone(self.solicitud.fecha_direccion_confirmada)
                self.assertFalse(DireccionCliente.objects.exists())

    def test_referencia_es_opcional(self):
        self.pagar()
        self.client.post(self.url, {**self.nueva, 'referencia': ''})
        self.solicitud.refresh_from_db()
        self.assertTrue(self.solicitud.direccion_entrega_confirmada)
        self.assertEqual(self.solicitud.referencia_entrega, '')

    def test_guardada_copia_direccion_y_referencia_y_permite_elegir_nueva(self):
        propia = self.guardar_direccion()
        ajena = self.guardar_direccion(self.otro, nombre='Dirección privada de otro')
        self.pagar()
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.context['form'].modo, 'guardada')
        self.assertContains(respuesta, propia.direccion)
        self.assertNotContains(respuesta, ajena.nombre)
        self.assertEqual(self.client.get(self.url + '?tipo=nueva').context['form'].modo, 'nueva')
        self.assertRedirects(self.client.post(self.url, {
            'tipo': 'guardada', 'direccion_guardada': propia.pk,
        }), self.detalle)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.direccion_entrega, propia.direccion)
        self.assertEqual(self.solicitud.referencia_entrega, propia.referencia)
        self.assertEqual(self.solicitud.nombre_direccion_entrega, propia.nombre)
        self.assertEqual(DireccionCliente.objects.filter(cliente=self.cliente).count(), 1)

    def test_guardada_ajena_eliminada_o_no_elegida_se_rechaza(self):
        ajena = self.guardar_direccion(self.otro)
        self.pagar()
        for valor in (ajena.pk, 999999, ''):
            respuesta = self.client.post(self.url, {'tipo': 'guardada', 'direccion_guardada': valor})
            self.assertIn('direccion_guardada', respuesta.context['form'].errors)
            self.solicitud.refresh_from_db()
            self.assertFalse(self.solicitud.direccion_entrega_confirmada)

    def test_editar_y_eliminar_guardada_conserva_snapshot_cliente_y_admin(self):
        propia = self.guardar_direccion()
        self.pagar()
        self.client.post(self.url, {'tipo': 'guardada', 'direccion_guardada': propia.pk})
        self.assertRedirects(self.client.post(reverse('configuraciones:direccion_editar', args=[propia.pk]), {
            'nombre': 'Nombre nuevo', 'direccion': 'Otra dirección', 'referencia': 'Otra referencia',
        }), reverse('configuraciones:mis_direcciones'))
        self.assertRedirects(self.client.post(reverse('configuraciones:direccion_eliminar', args=[propia.pk])),
                             reverse('configuraciones:mis_direcciones'))
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.direccion_entrega, propia.direccion)
        self.assertEqual(self.solicitud.referencia_entrega, propia.referencia)
        for usuario in (self.cliente, self.admin):
            self.client.force_login(usuario)
            respuesta = self.client.get(self.detalle)
            self.assertContains(respuesta, propia.direccion)
            self.assertContains(respuesta, propia.referencia)
            self.assertNotContains(respuesta, 'Otra dirección')

    def test_no_se_confirma_antes_de_completar_renta_y_deposito(self):
        for concepto in (None, 'renta'):
            if concepto:
                PagoAlquiler.objects.create(presupuesto=self.presupuesto, concepto=concepto, monto=100,
                                            metodo='efectivo', registrado_por=self.admin)
            self.assertEqual(self.client.get(self.url).status_code, 302)
            self.assertEqual(self.client.post(self.url, self.nueva).status_code, 302)
            self.solicitud.refresh_from_db()
            self.assertFalse(self.solicitud.direccion_entrega_confirmada)

    def test_no_confirma_en_estados_no_aprobados(self):
        self.pagar()
        for estado in ('Pendiente', 'Vencida', 'Rechazada', 'Cancelada'):
            SolicitudAlquiler.objects.filter(pk=self.solicitud.pk).update(estado=estado)
            self.assertEqual(self.client.post(self.url, self.nueva).status_code, 302)
            self.solicitud.refresh_from_db()
            self.assertFalse(self.solicitud.direccion_entrega_confirmada)

    def test_reenvio_no_reemplaza_snapshot_ni_duplica_guardada(self):
        self.pagar()
        datos = {**self.nueva, 'guardar': 'on', 'nombre': 'Obra'}
        self.client.post(self.url, datos)
        self.client.post(self.url, {**datos, 'direccion': 'Dirección cambiada'})
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.direccion_entrega, self.nueva['direccion'])
        self.assertEqual(DireccionCliente.objects.count(), 1)

    def test_relee_estado_bajo_bloqueo_antes_de_confirmar(self):
        from .views import bloquear_movimiento

        self.pagar()

        def cambia_estado(solicitud_id):
            SolicitudAlquiler.objects.filter(pk=solicitud_id).update(estado='Cancelada')
            return bloquear_movimiento(solicitud_id)

        with patch('apps.alquileres.views.bloquear_movimiento', side_effect=cambia_estado):
            respuesta = self.client.post(self.url, {**self.nueva, 'guardar': 'on', 'nombre': 'Obra'})
        self.assertContains(respuesta, 'El alquiler ya no está pendiente de dirección')
        self.solicitud.refresh_from_db()
        self.assertFalse(self.solicitud.direccion_entrega_confirmada)
        self.assertFalse(DireccionCliente.objects.exists())

    def test_direccion_eliminada_durante_confirmacion_no_se_copia(self):
        from .views import bloquear_movimiento

        propia = self.guardar_direccion()
        self.pagar()

        def elimina_direccion(solicitud_id):
            propia.delete()
            return bloquear_movimiento(solicitud_id)

        with patch('apps.alquileres.views.bloquear_movimiento', side_effect=elimina_direccion):
            respuesta = self.client.post(self.url, {'tipo': 'guardada', 'direccion_guardada': propia.pk})
        self.assertContains(respuesta, 'La dirección guardada ya no existe')
        self.solicitud.refresh_from_db()
        self.assertFalse(self.solicitud.direccion_entrega_confirmada)

    def test_fallo_guardar_snapshot_revierte_tambien_libreta(self):
        self.pagar()
        with patch.object(SolicitudAlquiler, 'save', side_effect=DatabaseError('fallo simulado')):
            respuesta = self.client.post(self.url, {**self.nueva, 'guardar': 'on', 'nombre': 'Obra'})
        self.assertContains(respuesta, 'No se guardaron cambios')
        self.assertFalse(DireccionCliente.objects.exists())
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.fecha_direccion_confirmada)

    def test_cliente_ajeno_no_accede_ni_confirma_alquiler_o_presupuesto(self):
        self.pagar()
        self.client.force_login(self.otro)
        for url in (self.detalle, self.url,
                    reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk])):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.nueva).status_code, 404)
        self.assertNotContains(self.client.get(reverse('alquileres:solicitud_lista')), self.detalle)

    def test_admin_y_tecnico_no_confirman_por_el_cliente(self):
        self.pagar()
        for usuario in (self.admin, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, self.nueva).status_code, 403)

    def test_admin_ve_aviso_y_post_directo_no_registra_salida_sin_direccion(self):
        self.pagar()
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.detalle)
        self.assertContains(respuesta, 'Pendiente de dirección de entrega')
        self.assertNotContains(respuesta, 'Registrar entrega de maquinaria')
        self.assertRedirects(self.client.post(reverse('alquileres:solicitud_salida', args=[self.solicitud.pk])), self.detalle)
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.fecha_salida)
        self.assertIsNone(self.solicitud.entregado_por)

    def test_salida_se_habilita_despues_de_confirmar_direccion(self):
        self.pagar()
        self.client.post(self.url, self.nueva)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.detalle), 'Registrar entrega de maquinaria')
        self.client.post(reverse('alquileres:solicitud_salida', args=[self.solicitud.pk]))
        self.solicitud.refresh_from_db()
        self.assertIsNotNone(self.solicitud.fecha_salida)
        self.assertEqual(self.solicitud.estado_cliente, 'En uso')

    def test_anteriores_sin_direccion_mantienen_en_uso_devuelto_y_permiten_retorno(self):
        self.pagar()
        self.solicitud.fecha_salida = timezone.now() - timedelta(hours=1)
        self.solicitud.entregado_por = self.admin
        self.solicitud.save(update_fields=['fecha_salida', 'entregado_por'])
        for usuario in (self.cliente, self.admin):
            self.client.force_login(usuario)
            self.assertContains(self.client.get(self.detalle), 'Dirección no registrada (alquiler anterior).')
            self.assertNotContains(self.client.get(self.detalle), 'Indicar dirección de entrega')
        self.assertEqual(self.solicitud.estado_cliente, 'En uso')
        self.client.post(reverse('alquileres:solicitud_retorno', args=[self.solicitud.pk]),
                         {'horas_uso_actualizadas': '5.0'})
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado_cliente, 'Devuelto')
        self.assertContains(self.client.get(self.detalle), 'Dirección no registrada (alquiler anterior).')

    def test_pago_anterior_sin_fecha_confirmacion_tambien_pide_direccion(self):
        self.pagar()
        SolicitudAlquiler.objects.filter(pk=self.solicitud.pk).update(
            fecha_confirmacion=None, fecha_revision=timezone.now() - timedelta(days=10),
        )
        self.assertContains(self.client.get(self.detalle), 'Indicar dirección de entrega')
        self.assertRedirects(self.client.post(self.url, self.nueva), self.detalle)

    def test_configuraciones_crud_solo_propias_y_borrado_requiere_post(self):
        ajena = self.guardar_direccion(self.otro, nombre='Dirección privada')
        lista = reverse('configuraciones:mis_direcciones')
        self.assertContains(self.client.get(reverse('configuraciones:indice')), 'Mis direcciones')
        self.assertRedirects(self.client.post(reverse('configuraciones:direccion_agregar'), {
            'nombre': 'Obra nueva', 'direccion': self.nueva['direccion'], 'referencia': '',
            'cliente': self.otro.pk,
        }), lista)
        propia = DireccionCliente.objects.get(cliente=self.cliente)
        self.assertNotContains(self.client.get(lista), ajena.nombre)
        for accion in ('direccion_editar', 'direccion_eliminar'):
            url = reverse('configuraciones:' + accion, args=[ajena.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, self.nueva).status_code, 404)
        url = reverse('configuraciones:direccion_eliminar', args=[propia.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(DireccionCliente.objects.filter(pk=propia.pk).exists())
        self.assertRedirects(self.client.post(url), lista)
        self.assertFalse(DireccionCliente.objects.filter(pk=propia.pk).exists())

    def test_configuraciones_restringe_roles_y_rechaza_campos_vacios(self):
        propia = self.guardar_direccion()
        for url in (reverse('configuraciones:direccion_agregar'),
                    reverse('configuraciones:direccion_editar', args=[propia.pk])):
            respuesta = self.client.post(url, {'nombre': ' ', 'direccion': ' '})
            self.assertIn('nombre', respuesta.context['form'].errors)
            self.assertIn('direccion', respuesta.context['form'].errors)
        urls = (reverse('configuraciones:mis_direcciones'), reverse('configuraciones:direccion_agregar'),
                reverse('configuraciones:direccion_editar', args=[propia.pk]),
                reverse('configuraciones:direccion_eliminar', args=[propia.pk]))
        for usuario in (self.admin, self.tecnico):
            self.client.force_login(usuario)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_anonimo_se_redirige_y_confirmacion_exige_csrf(self):
        self.client.logout()
        for url in (self.url, self.detalle, reverse('configuraciones:mis_direcciones')):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.pagar()
        cliente_csrf = Client(enforce_csrf_checks=True)
        cliente_csrf.force_login(self.cliente)
        self.assertEqual(cliente_csrf.post(self.url, self.nueva).status_code, 403)
