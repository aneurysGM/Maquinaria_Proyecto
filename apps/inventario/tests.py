from io import BytesIO
import tempfile

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado, permisos_panel
from .forms import MaquinariaImagenFormSet
from .models import Categoria, Maquinaria, MaquinariaImagen, Unidad


class PermisosMaquinariaTests(TestCase):
    def crear_usuario(self, email, rol, **campos):
        return UsuarioPersonalizado.objects.create_user(
            email=email,
            password='test-password',
            rol=rol,
            **campos,
        )

    def test_permisos_de_maquinaria_se_alinean_con_roles_vigentes(self):
        administrador = self.crear_usuario(
            'admin@example.com', RolUsuario.ADMINISTRADOR
        )
        cliente = self.crear_usuario('cliente@example.com', RolUsuario.CLIENTE)
        tecnico = self.crear_usuario('tecnico@example.com', RolUsuario.TECNICO)
        tercero = self.crear_usuario('tercero@example.com', RolUsuario.TERCERO)
        sin_rol = self.crear_usuario('sin-rol@example.com', '')

        self.assertTrue(administrador.puede_consultar_maquinaria)
        self.assertTrue(administrador.puede_registrar_maquinaria)
        self.assertTrue(cliente.puede_consultar_maquinaria)
        self.assertFalse(cliente.puede_registrar_maquinaria)
        self.assertTrue(tecnico.puede_consultar_maquinaria)
        self.assertFalse(tecnico.puede_registrar_maquinaria)
        self.assertFalse(tercero.puede_consultar_maquinaria)
        self.assertFalse(tercero.puede_registrar_maquinaria)
        self.assertFalse(sin_rol.puede_consultar_maquinaria)
        self.assertFalse(sin_rol.puede_registrar_maquinaria)

        self.assertEqual(
            permisos_panel(cliente)['puede_consultar_maquinaria'],
            cliente.puede_consultar_maquinaria,
        )

    def test_panel_muestra_enlaces_segun_permisos(self):
        administrador = self.crear_usuario(
            'admin@example.com', RolUsuario.ADMINISTRADOR, first_name='Ana'
        )
        self.client.force_login(administrador)

        respuesta = self.client.get(reverse('cuentas:dashboard'))

        self.assertContains(respuesta, 'Ana')
        self.assertContains(respuesta, reverse('inventario:maquinaria_lista'))
        self.assertContains(respuesta, reverse('inventario:maquinaria_crear'))

    def test_consulta_esta_permitida_a_roles_vigentes_y_registro_solo_a_admin(self):
        cliente = self.crear_usuario('cliente@example.com', RolUsuario.CLIENTE)
        self.client.force_login(cliente)

        self.assertEqual(
            self.client.get(reverse('inventario:maquinaria_lista')).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse('inventario:maquinaria_crear')).status_code,
            403,
        )

    def test_cuenta_sin_rol_no_puede_consultar_inventario(self):
        usuario = self.crear_usuario('sin-rol@example.com', '')
        self.client.force_login(usuario)

        self.assertEqual(
            self.client.get(reverse('inventario:maquinaria_lista')).status_code,
            403,
        )


class CatalogoPanelTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-catalogo@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-catalogo@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.categoria, _ = Categoria.objects.get_or_create(nombre='Excavadoras')

    def crear_unidad(self, codigo, nombre, registrada_por, estado='Disponible'):
        maquinaria = Maquinaria.objects.create(
            categoria=self.categoria,
            codigo=codigo,
            nombre=nombre,
            descripcion='Equipo para trabajos de excavación.',
            costo_adquisicion=99000,
            tarifa_diaria=750,
            tarifa_semanal=4500,
            tarifa_mensual=15000,
            deposito_garantia=3000,
            registrada_por=registrada_por,
        )
        return Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie=f'SERIE-{codigo}',
            ubicacion_actual='Santo Domingo',
            estado=estado,
        )

    def test_panel_admin_muestra_solo_sus_unidades_disponibles_y_costo_interno(self):
        propia = self.crear_unidad('ADM-001', 'Excavadora propia', self.admin)
        self.crear_unidad('ADM-002', 'Excavadora ajena', self.cliente)
        historica = self.crear_unidad('ADM-005', 'Excavadora histórica', None)
        self.crear_unidad(
            'ADM-003', 'Excavadora alquilada', self.admin, estado='Alquilado'
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse('cuentas:dashboard'))

        self.assertContains(respuesta, propia.maquinaria.nombre)
        self.assertContains(respuesta, historica.maquinaria.nombre)
        self.assertContains(respuesta, '$99000,00')
        self.assertNotContains(respuesta, 'Excavadora ajena')
        self.assertNotContains(respuesta, 'Excavadora alquilada')

    def test_cliente_ve_tarifas_y_deposito_pero_no_costo_adquisicion(self):
        unidad = self.crear_unidad('CLI-001', 'Excavadora para alquilar', self.admin)
        self.client.force_login(self.cliente)

        respuesta = self.client.get(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk])
        )

        self.assertContains(respuesta, '$750,00')
        self.assertContains(respuesta, '$3000,00')
        self.assertNotContains(respuesta, '$99000,00')
        self.assertContains(respuesta, 'Equipo para trabajos de excavación.')
        self.assertContains(respuesta, reverse(
            'alquileres:solicitud_registrar', args=[unidad.pk]
        ))
        respuesta_solicitud = self.client.get(
            reverse('alquileres:solicitud_registrar', args=[unidad.pk])
        )
        self.assertEqual(respuesta_solicitud.status_code, 200)

    def test_cliente_puede_publicar_comentario(self):
        unidad = self.crear_unidad('CLI-002', 'Excavadora con comentarios', self.admin)
        self.client.force_login(self.cliente)

        respuesta = self.client.post(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk]),
            {'texto': 'El equipo llegó en buen estado.'},
        )

        self.assertRedirects(
            respuesta,
            reverse('inventario:maquinaria_detalle', args=[unidad.pk]),
        )
        self.assertEqual(unidad.maquinaria.comentarios.count(), 1)
        self.assertEqual(
            unidad.maquinaria.comentarios.get().cliente,
            self.cliente,
        )
        respuesta_detalle = self.client.get(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk])
        )
        self.assertContains(respuesta_detalle, 'El equipo llegó en buen estado.')

    def test_administrador_no_puede_publicar_comentario_de_cliente(self):
        unidad = self.crear_unidad('ADM-004', 'Excavadora administrativa', self.admin)
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk]),
            {'texto': 'Comentario de administrador.'},
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(unidad.maquinaria.comentarios.count(), 0)

    def test_registro_administrativo_guarda_responsable_descripcion_e_imagen(self):
        image_buffer = BytesIO()
        Image.new('RGB', (2, 2), color='orange').save(image_buffer, format='PNG')
        image_buffer.seek(0)
        imagen = SimpleUploadedFile(
            'excavadora.png',
            image_buffer.read(),
            content_type='image/png',
        )
        prefix = MaquinariaImagenFormSet().prefix
        data = {
            'categoria': self.categoria.pk,
            'codigo': 'IMG-001',
            'nombre': 'Excavadora con galería',
            'descripcion': 'Descripción de prueba de la excavadora.',
            'marca': 'Marca',
            'modelo': 'Modelo',
            'costo_adquisicion': '99000',
            'tarifa_diaria': '750',
            'tarifa_semanal': '4500',
            'tarifa_mensual': '15000',
            'deposito_garantia': '3000',
            'numero_serie': 'SERIE-IMG-001',
            'estado': 'Disponible',
            'horas_uso': '0',
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': 'Santo Domingo',
            f'{prefix}-TOTAL_FORMS': '2',
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '8',
            f'{prefix}-0-texto_alternativo': 'Excavadora en obra',
            f'{prefix}-1-texto_alternativo': '',
            f'{prefix}-0-imagen': imagen,
        }
        self.client.force_login(self.admin)

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                respuesta = self.client.post(
                    reverse('inventario:maquinaria_crear'),
                    data,
                )
                maquinaria = Maquinaria.objects.get(codigo='IMG-001')
                respuesta_detalle = self.client.get(
                    reverse(
                        'inventario:maquinaria_detalle',
                        args=[maquinaria.unidades.get().pk],
                    )
                )
                self.assertContains(respuesta_detalle, 'Excavadora en obra')

        self.assertRedirects(respuesta, reverse('inventario:maquinaria_lista'))
        self.assertEqual(maquinaria.registrada_por, self.admin)
        self.assertEqual(
            maquinaria.descripcion,
            'Descripción de prueba de la excavadora.',
        )
        self.assertEqual(MaquinariaImagen.objects.filter(maquinaria=maquinaria).count(), 1)
