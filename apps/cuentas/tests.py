from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import RolUsuario, UsuarioPersonalizado


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
