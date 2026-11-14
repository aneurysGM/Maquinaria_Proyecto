from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.alquileres.tests_datos import DatosIntegracion
from .models import RolUsuario, UsuarioPersonalizado


class DashboardPendientesTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def comprobar_contador(self, esperado):
        self.client.force_login(self.admin)
        respuesta = self.client.get(reverse('cuentas:dashboard'))
        self.assertEqual(respuesta.context['kpis']['solicitudes_pendientes'], esperado)
        self.assertContains(respuesta, f'''
            <div class="kpi-num">{esperado}</div>
            <div class="small text-secondary">Solicitudes por revisar</div>
        ''', html=True)

    def test_cuenta_todas_las_pendientes_y_excluye_otros_estados(self):
        for cliente in (self.cliente, self.otro, self.cliente):
            self.crear_solicitud(cliente=cliente)
        for estado in ('Aprobada', 'Rechazada', 'Vencida'):
            self.crear_solicitud(estado=estado)
        self.comprobar_contador(3)

    def test_sin_pendientes_la_tarjeta_muestra_cero(self):
        for estado in ('Aprobada', 'Rechazada', 'Vencida'):
            self.crear_solicitud(estado=estado)
        self.comprobar_contador(0)


class SuspensionClientesTests(TestCase):
    def test_suspension_vencida_se_reactiva_al_iniciar_sesion(self):
        usuario = UsuarioPersonalizado.objects.create_user(
            email='suspension-vencida@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
            is_active=False,
            suspension_hasta=timezone.localdate() - timedelta(days=1),
        )

        respuesta = self.client.post(
            reverse('cuentas:login'),
            {'username': usuario.email, 'password': 'test-password'},
        )

        usuario.refresh_from_db()
        self.assertRedirects(respuesta, reverse('cuentas:dashboard'))
        self.assertTrue(usuario.is_active)
        self.assertIsNone(usuario.suspension_hasta)

    def test_inicio_de_sesion_respeta_el_destino_solicitado(self):
        usuario = UsuarioPersonalizado.objects.create_user(
            email='cliente-next@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        destino = reverse('alquileres:solicitud_registrar', args=[123])

        respuesta = self.client.post(
            reverse('cuentas:login'),
            {
                'username': usuario.email,
                'password': 'test-password',
                'next': destino,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, destino)

    def test_cuenta_desactivada_manualmente_sin_plazo_no_se_reactiva(self):
        usuario = UsuarioPersonalizado.objects.create_user(
            email='desactivado-manual@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
            is_active=False,
        )

        respuesta = self.client.post(
            reverse('cuentas:login'),
            {'username': usuario.email, 'password': 'test-password'},
        )

        usuario.refresh_from_db()
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(usuario.is_active)
