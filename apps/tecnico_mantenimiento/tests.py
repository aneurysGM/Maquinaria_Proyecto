from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad


class GestionTecnicosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-tecnicos@example.com',
            password='PruebaSegura!2026',
            first_name='Admin',
            rol=RolUsuario.ADMINISTRADOR,
        )
        cls.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-tecnicos@example.com',
            password='PruebaSegura!2026',
            first_name='Cliente',
            rol=RolUsuario.CLIENTE,
        )
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-panel@example.com',
            password='PruebaSegura!2026',
            first_name='Técnico',
            rol=RolUsuario.TECNICO,
            especialidad='Motores diésel',
        )

    def test_administrador_crea_tecnico_con_contrasena_definida_por_el(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse('tecnico_mantenimiento:crear'),
            {
                'first_name': 'Ana',
                'last_name': 'Técnica',
                'email': 'ana-tecnica@example.com',
                'telefono': '809-555-0101',
                'especialidad': 'Sistema hidráulico',
                'password1': 'Firme!Girasol_2026',
                'password2': 'Firme!Girasol_2026',
            },
        )

        self.assertRedirects(respuesta, reverse('tecnico_mantenimiento:lista'))
        tecnico = UsuarioPersonalizado.objects.get(email='ana-tecnica@example.com')
        self.assertEqual(tecnico.rol, RolUsuario.TECNICO)
        self.assertEqual(tecnico.first_name, 'Ana')
        self.assertEqual(tecnico.last_name, 'Técnica')
        self.assertEqual(tecnico.telefono, '809-555-0101')
        self.assertEqual(tecnico.especialidad, 'Sistema hidráulico')
        self.assertTrue(tecnico.check_password('Firme!Girasol_2026'))
        self.assertFalse(tecnico.is_staff)
        self.assertTrue(tecnico.primer_inicio_sesion)

    def test_tecnico_debe_cambiar_contrasena_antes_de_acceder_al_sistema(self):
        tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-temporal@example.com',
            password='Temporal!Clave_2026',
            rol=RolUsuario.TECNICO,
            primer_inicio_sesion=True,
        )

        respuesta_login = self.client.post(
            reverse('cuentas:login'),
            {
                'username': tecnico.email,
                'password': 'Temporal!Clave_2026',
                'next': reverse('tecnico_mantenimiento:dashboard'),
            },
        )
        self.assertRedirects(
            respuesta_login,
            reverse('configuraciones:cambiar_contrasena'),
        )

        respuesta_dashboard = self.client.get(
            reverse('tecnico_mantenimiento:dashboard'),
        )
        self.assertRedirects(
            respuesta_dashboard,
            reverse('configuraciones:cambiar_contrasena'),
        )

        respuesta_cambio = self.client.post(
            reverse('configuraciones:cambiar_contrasena'),
            {
                'old_password': 'Temporal!Clave_2026',
                'new_password1': 'Nueva!ClaveTecnica_2026',
                'new_password2': 'Nueva!ClaveTecnica_2026',
            },
        )

        self.assertRedirects(
            respuesta_cambio,
            reverse('tecnico_mantenimiento:dashboard'),
        )
        tecnico.refresh_from_db()
        self.assertFalse(tecnico.primer_inicio_sesion)
        self.assertTrue(tecnico.check_password('Nueva!ClaveTecnica_2026'))
        self.assertEqual(
            self.client.get(reverse('tecnico_mantenimiento:dashboard')).status_code,
            200,
        )

    def test_tecnico_temporal_puede_cerrar_sesion_sin_cambiar_contrasena(self):
        tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-cierre@example.com',
            password='Temporal!Clave_2026',
            rol=RolUsuario.TECNICO,
            primer_inicio_sesion=True,
        )
        self.client.force_login(tecnico)

        respuesta = self.client.post(reverse('cuentas:logout'))

        self.assertEqual(respuesta.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_tarjeta_de_perfil_muestra_iniciales_nombre_y_rol_segun_corresponda(self):
        usuarios = (
            (
                self.admin,
                reverse('inventario:maquinaria_lista'),
                'AM',
                'Ana Martínez',
                'Administrador',
            ),
            (
                self.cliente,
                reverse('inventario:maquinaria_lista'),
                'CC',
                'Carla Castillo',
                None,
            ),
            (
                self.tecnico,
                reverse('tecnico_mantenimiento:dashboard'),
                'TT',
                'Tomás Torres',
                'Técnico',
            ),
        )
        self.admin.first_name = 'Ana'
        self.admin.last_name = 'Martínez'
        self.admin.save(update_fields=('first_name', 'last_name'))
        self.cliente.first_name = 'Carla'
        self.cliente.last_name = 'Castillo'
        self.cliente.save(update_fields=('first_name', 'last_name'))
        self.tecnico.first_name = 'Tomás'
        self.tecnico.last_name = 'Torres'
        self.tecnico.save(update_fields=('first_name', 'last_name'))

        for usuario, url, iniciales, nombre, rol in usuarios:
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, f'class="mq-avatar">{iniciales}</div>')
                self.assertContains(respuesta, nombre)
                if rol:
                    self.assertContains(respuesta, f'<span>{rol}</span>')
                else:
                    self.assertNotContains(respuesta, '<span>Cliente</span>')

    def test_solo_administrador_puede_listar_o_crear_tecnicos(self):
        for usuario in (self.cliente, self.tecnico):
            with self.subTest(rol=usuario.rol):
                self.client.force_login(usuario)
                lista = self.client.get(reverse('tecnico_mantenimiento:lista'))
                crear = self.client.get(reverse('tecnico_mantenimiento:crear'))
                self.assertEqual(lista.status_code, 403)
                self.assertEqual(crear.status_code, 403)

    def test_registro_publico_no_permite_elegir_rol_tecnico(self):
        respuesta = self.client.post(
            reverse('cuentas:registro'),
            {
                'first_name': 'Registro Público',
                'last_name': 'Prueba',
                'email': 'registro-publico@example.com',
                'telefono': '809-555-0102',
                'password1': 'Firme!Girasol_2026',
                'password2': 'Firme!Girasol_2026',
                'rol': RolUsuario.TECNICO,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        usuario = UsuarioPersonalizado.objects.get(
            email='registro-publico@example.com',
        )
        self.assertEqual(usuario.rol, RolUsuario.CLIENTE)

    def test_tecnico_usa_dashboard_propio_y_puede_cambiar_contrasena(self):
        self.client.force_login(self.tecnico)

        inicio = self.client.get(reverse('cuentas:dashboard'))
        dashboard = self.client.get(reverse('tecnico_mantenimiento:dashboard'))
        cambio = self.client.post(
            reverse('configuraciones:cambiar_contrasena'),
            {
                'old_password': 'PruebaSegura!2026',
                'new_password1': 'Nueva!ClaveTecnica_2026',
                'new_password2': 'Nueva!ClaveTecnica_2026',
            },
        )

        self.assertRedirects(inicio, reverse('tecnico_mantenimiento:dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Motores diésel')
        self.assertContains(dashboard, reverse('mantenimiento:mantenimiento_lista'))
        self.assertRedirects(cambio, reverse('configuraciones:indice'))
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.check_password('Nueva!ClaveTecnica_2026'))

    def test_cliente_no_puede_abrir_dashboard_tecnico(self):
        self.client.force_login(self.cliente)

        respuesta = self.client.get(reverse('tecnico_mantenimiento:dashboard'))

        self.assertEqual(respuesta.status_code, 403)

    def test_tecnico_consulta_estado_sin_ver_costo_de_adquisicion(self):
        categoria = Categoria.objects.create(nombre='Equipos restringidos')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='TEC-001',
            nombre='Excavadora de prueba',
            costo_adquisicion=9876543,
            tarifa_diaria=1000,
            tarifa_semanal=7000,
            tarifa_mensual=30000,
        )
        unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='TEC-SERIE-001',
            estado='Mantenimiento',
            ubicacion_actual='Taller',
        )
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk]),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'En mantenimiento')
        self.assertNotContains(respuesta, '9876543')
