from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from .models import SolicitudAlquiler


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AvisoVencimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-aviso@example.com', rol=RolUsuario.ADMINISTRADOR,
        )
        cls.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-aviso@example.com', rol=RolUsuario.CLIENTE,
        )
        cls.otro_cliente = UsuarioPersonalizado.objects.create_user(
            email='otro-aviso@example.com', rol=RolUsuario.CLIENTE,
        )
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-aviso@example.com', rol=RolUsuario.TECNICO,
        )
        cls.superusuario = UsuarioPersonalizado.objects.create_superuser(
            email='super-aviso@example.com', password='pass',
        )
        categoria = Categoria.objects.create(nombre='Equipos para aviso')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='AV-01', nombre='Equipo vencido',
            tarifa_diaria=100, tarifa_semanal=500, tarifa_mensual=1500,
            deposito_garantia=100,
        )
        cls.unidad = Unidad.objects.create(maquinaria=maquinaria, numero_serie='AV-01')
        hoy = timezone.localdate()
        cls.solicitud = SolicitudAlquiler.objects.create(
            cliente=cls.cliente, unidad=cls.unidad, plan='semanal', cantidad=2,
            fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=13),
            estado='Vencida', fecha_revision=timezone.now() - timedelta(days=6),
        )
        cls.presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=cls.solicitud, tarifa_periodo=500, importe_renta=1000,
            deposito_garantia=100,
        )

    def setUp(self):
        self.aviso_url = reverse('alquileres:solicitud_avisar_vencimiento', args=[self.solicitud.pk])
        self.registro_url = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk])
        self.lista_url = reverse('alquileres:solicitud_lista')
        self.presupuesto_url = reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk])

    def test_acciones_dependen_del_rol_en_lista_y_presupuesto(self):
        for usuario, texto, ausente in (
            (self.admin, 'Enviar solicitud', 'Volver a solicitar'),
            (self.cliente, 'Volver a solicitar', 'Enviar solicitud'),
        ):
            self.client.force_login(usuario)
            for url in (self.lista_url, self.presupuesto_url):
                with self.subTest(usuario=usuario.email, url=url):
                    respuesta = self.client.get(url)
                    self.assertContains(respuesta, texto)
                    self.assertNotContains(respuesta, ausente)

    def test_solo_cliente_puede_crear_solicitudes(self):
        for usuario in (self.admin, self.tecnico, self.superusuario):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.registro_url).status_code, 403)
            self.assertEqual(self.client.post(self.registro_url, {}).status_code, 403)
            if usuario.es_administrador:
                pagina = self.client.get(reverse('inventario:maquinaria_detalle', args=[self.unidad.pk]))
                self.assertNotContains(pagina, 'Solicitar alquiler')
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(self.registro_url).status_code, 200)

    def test_admin_envia_aviso_persistente_y_correo_al_cliente(self):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(self.aviso_url, {'next': self.lista_url})
        self.assertRedirects(respuesta, self.lista_url)
        self.solicitud.refresh_from_db()
        self.assertIsNotNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertEqual(self.solicitud.estado, 'Vencida')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.cliente.email])
        self.assertIn('Equipo vencido', mail.outbox[0].body)
        self.client.force_login(self.cliente)
        self.assertContains(self.client.get(self.lista_url), 'Mensaje del administrador')
        self.assertContains(self.client.get(self.presupuesto_url), 'Mensaje del administrador')
        self.client.force_login(self.otro_cliente)
        self.assertNotContains(self.client.get(self.lista_url), 'Equipo vencido')
        self.assertEqual(self.client.get(self.presupuesto_url).status_code, 404)

    def test_aviso_requiere_admin_post_y_csrf(self):
        for usuario in (self.cliente, self.otro_cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(self.aviso_url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.aviso_url).status_code, 405)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(self.aviso_url).status_code, 403)
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertEqual(len(mail.outbox), 0)

    def test_solo_se_avisa_si_esta_vencida_incluso_sin_expirar_en_bd(self):
        self.client.force_login(self.admin)
        self.solicitud.estado = 'Aprobada'
        self.solicitud.fecha_revision = timezone.now()
        self.solicitud.save(update_fields=['estado', 'fecha_revision'])
        self.client.post(self.aviso_url)
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertEqual(len(mail.outbox), 0)
        self.solicitud.fecha_revision = timezone.now() - timedelta(days=6)
        self.solicitud.save(update_fields=['fecha_revision'])
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.aviso_url)
        self.solicitud.refresh_from_db()
        self.assertIsNotNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertEqual(len(mail.outbox), 1)

    def test_solicitud_pagada_no_permite_aviso_aunque_haya_pasado_el_plazo(self):
        self.client.force_login(self.admin)
        self.solicitud.estado = 'Aprobada'
        self.solicitud.save(update_fields=['estado'])
        for concepto, monto in (('renta', 1000), ('deposito', 100)):
            PagoAlquiler.objects.create(
                presupuesto=self.presupuesto, concepto=concepto, monto=monto,
                metodo='efectivo', registrado_por=self.admin,
            )
        self.client.post(self.aviso_url)
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertEqual(len(mail.outbox), 0)
        self.assertNotContains(self.client.get(self.lista_url), 'Enviar solicitud')

    def test_destino_externo_no_se_acepta(self):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(self.aviso_url, {'next': 'https://example.com/'})
        self.assertRedirects(respuesta, self.lista_url)

    def test_fallo_correo_deja_aviso_visible_y_muestra_error(self):
        self.client.force_login(self.admin)
        with self.assertLogs('apps.alquileres.notificaciones', level='ERROR'):
            with patch('apps.alquileres.notificaciones.send_mail', side_effect=OSError('SMTP')):
                with patch('apps.alquileres.views.transaction.on_commit', side_effect=lambda callback: callback()):
                    respuesta = self.client.post(self.aviso_url)
        respuesta = self.client.get(respuesta.url)
        self.solicitud.refresh_from_db()
        self.assertIsNotNone(self.solicitud.fecha_aviso_vencimiento)
        self.assertContains(respuesta, 'no se pudo enviar el correo')
