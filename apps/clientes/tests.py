from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado


class EstadoClienteTests(TestCase):
    def setUp(self):
        self.administrador = UsuarioPersonalizado.objects.create_user(
            email='admin-clientes@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-estado@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )

    def cambiar_estado(self, **datos):
        return self.client.post(
            reverse('clientes:cliente_cambiar_estado', args=[self.cliente.pk]),
            datos,
        )

    def test_administrador_inactiva_y_reactiva_cliente_manualmente(self):
        self.client.force_login(self.administrador)

        respuesta = self.cambiar_estado(
            accion='inactivar',
            motivo='Solicitud personal del cliente.',
        )

        self.assertRedirects(
            respuesta,
            reverse('clientes:cliente_detalle', args=[self.cliente.pk]),
        )
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)
        self.assertEqual(
            self.cliente.motivo_inactivacion,
            'Solicitud personal del cliente.',
        )

        self.cambiar_estado(accion='activar')
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        self.assertEqual(self.cliente.motivo_inactivacion, '')

    def test_inactivacion_exige_motivo(self):
        self.client.force_login(self.administrador)

        self.cambiar_estado(accion='inactivar', motivo=' ')

        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)

    def test_cliente_no_puede_cambiar_su_propio_estado(self):
        self.client.force_login(self.cliente)

        respuesta = self.cambiar_estado(
            accion='inactivar',
            motivo='Intento no autorizado.',
        )

        self.assertEqual(respuesta.status_code, 403)
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
