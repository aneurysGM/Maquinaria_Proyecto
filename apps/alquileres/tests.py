from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from .models import SolicitudAlquiler


class SolicitudesAlquilerTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        categoria, _ = Categoria.objects.get_or_create(nombre='Excavadoras')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='ALQ-001',
            nombre='Excavadora para alquiler',
            descripcion='Equipo para obras.',
            costo_adquisicion=99000,
            tarifa_diaria=750,
            tarifa_semanal=4500,
            tarifa_mensual=15000,
            deposito_garantia=3000,
            registrada_por=self.admin,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SERIE-ALQ-001',
            ubicacion_actual='Santo Domingo',
            estado='Disponible',
        )

    def test_cliente_puede_enviar_solicitud_y_verla_en_su_bandeja(self):
        self.client.force_login(self.cliente)
        inicio = timezone.localdate() + timedelta(days=1)
        fin = inicio + timedelta(days=2)

        respuesta = self.client.post(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
            {
                'fecha_inicio': inicio.isoformat(),
                'fecha_fin': fin.isoformat(),
                'comentario': 'Obra de prueba',
            },
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)
        solicitud = SolicitudAlquiler.objects.get()
        self.assertEqual(solicitud.cliente, self.cliente)
        self.assertEqual(solicitud.unidad, self.unidad)
        self.assertContains(respuesta, 'Obra de prueba')
        self.assertContains(respuesta, 'Pendiente')

    def test_tecnico_no_puede_consultar_bandeja_de_solicitudes(self):
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_puede_revisar_solicitudes_pendientes(self):
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            fecha_inicio=timezone.localdate() + timedelta(days=1),
            fecha_fin=timezone.localdate() + timedelta(days=2),
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertContains(respuesta, 'Solicitudes recibidas', status_code=200)
        self.assertContains(respuesta, f'name="decision" value="Aprobada"')
        self.assertContains(respuesta, f'action="/alquileres/solicitudes/resolver/{solicitud.pk}/"')
