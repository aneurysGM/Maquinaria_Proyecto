from django.test import TestCase
from django.urls import reverse

from apps.alquileres.models import SolicitudAlquiler
from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad


class GestionClientesTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-clientes@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-activo@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
            first_name='Carla',
            last_name='Cliente',
            telefono='809-555-0101',
        )
        self.cliente_inactivo = UsuarioPersonalizado.objects.create_user(
            email='cliente-inactivo@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
            is_active=False,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-clientes@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        categoria, _ = Categoria.objects.get_or_create(nombre='Excavadoras')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='CLI-001',
            nombre='Excavadora de historial',
            descripcion='Excavadora para pruebas.',
            costo_adquisicion=50000,
            tarifa_diaria=500,
            tarifa_semanal=3000,
            tarifa_mensual=10000,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SERIE-CLI-001',
            ubicacion_actual='Santo Domingo',
        )

    def test_solo_administrador_puede_ver_clientes(self):
        url = reverse('clientes:cliente_lista')

        self.assertRedirects(
            self.client.get(url),
            f'{reverse("cuentas:login")}?next={url}',
        )

        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.admin)
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.cliente.email)
        self.assertContains(respuesta, self.cliente_inactivo.email)
        self.assertContains(respuesta, 'Activa')
        self.assertContains(respuesta, 'Inactiva')

    def test_menu_de_clientes_aparece_para_administrador_y_enlaza_al_listado(self):
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse('cuentas:dashboard'))

        self.assertContains(respuesta, reverse('clientes:cliente_lista'))

    def test_filtro_separa_clientes_activos_e_inactivos(self):
        self.client.force_login(self.admin)

        activos = self.client.get(
            reverse('clientes:cliente_lista'), {'estado': 'activos'}
        )
        self.assertContains(activos, self.cliente.email)
        self.assertNotContains(activos, self.cliente_inactivo.email)

        inactivos = self.client.get(
            reverse('clientes:cliente_lista'), {'estado': 'inactivos'}
        )
        self.assertContains(inactivos, self.cliente_inactivo.email)
        self.assertNotContains(inactivos, self.cliente.email)

    def test_detalle_muestra_solicitudes_del_cliente_seleccionado(self):
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            fecha_inicio='2026-12-01',
            fecha_fin='2026-12-03',
            comentario='Obra de prueba',
            estado='Pendiente',
        )
        otro_cliente = UsuarioPersonalizado.objects.create_user(
            email='otro-cliente@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(
            reverse('clientes:cliente_detalle', args=[self.cliente.pk])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.unidad.maquinaria.nombre)
        self.assertContains(respuesta, self.unidad.numero_serie)
        self.assertContains(respuesta, solicitud.comentario)
        self.assertContains(respuesta, 'Pendiente')
        self.assertNotContains(respuesta, otro_cliente.email)

    def test_detalle_no_permite_consultar_usuarios_que_no_son_clientes(self):
        self.client.force_login(self.admin)

        respuesta = self.client.get(
            reverse('clientes:cliente_detalle', args=[self.tecnico.pk])
        )

        self.assertEqual(respuesta.status_code, 404)
