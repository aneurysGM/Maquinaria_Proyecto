from io import BytesIO
import tempfile
from urllib.parse import parse_qs, urlparse

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado, permisos_panel
from .forms import MaquinariaImagenFormSet, MaquinariaIntegralForm
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

        respuesta_lista = self.client.get(reverse('inventario:maquinaria_lista'))
        self.assertEqual(respuesta_lista.status_code, 200)
        self.assertNotContains(respuesta_lista, 'Gestionar Categorías')
        self.assertNotContains(respuesta_lista, 'Registrar Maquinaria')

        for ruta in (
            'inventario:categoria_lista',
            'inventario:categoria_crear',
            'inventario:maquinaria_crear',
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(
                    self.client.get(reverse(ruta)).status_code,
                    403,
                )

    def test_solo_administrador_ve_enlaces_de_gestion_y_accede_a_categorias(self):
        administrador = self.crear_usuario(
            'admin@example.com', RolUsuario.ADMINISTRADOR
        )
        self.client.force_login(administrador)

        respuesta_lista = self.client.get(reverse('inventario:maquinaria_lista'))

        self.assertEqual(respuesta_lista.status_code, 200)
        self.assertContains(respuesta_lista, 'Gestionar Categorías')
        self.assertContains(respuesta_lista, 'Registrar Maquinaria')
        self.assertEqual(
            self.client.get(reverse('inventario:categoria_lista')).status_code,
            200,
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

    def test_catalogo_publico_es_accesible_desde_inicio(self):
        unidad = self.crear_unidad(
            'PUB-001', 'Excavadora pública', self.admin
        )
        self.crear_unidad(
            'PUB-002', 'Excavadora en mantenimiento', self.admin,
            estado='Mantenimiento',
        )
        self.crear_unidad(
            'PUB-003', 'Excavadora fuera de servicio', self.admin,
            estado='Baja',
        )

        inicio = self.client.get(reverse('index'))
        self.assertEqual(inicio.status_code, 200)
        self.assertContains(inicio, reverse('catalogo'))
        self.assertNotContains(inicio, 'Excavadora en mantenimiento')
        self.assertNotContains(inicio, 'Excavadora fuera de servicio')

        catalogo = self.client.get(reverse('catalogo'))
        self.assertEqual(catalogo.status_code, 200)
        self.assertContains(catalogo, unidad.maquinaria.nombre)
        self.assertNotContains(catalogo, 'Excavadora en mantenimiento')
        self.assertNotContains(catalogo, 'Excavadora fuera de servicio')
        self.assertContains(
            catalogo,
            reverse('inventario:maquinaria_detalle', args=[unidad.pk]),
        )

    def test_visitante_puede_ver_detalle_y_debe_iniciar_sesion_para_solicitar(self):
        unidad = self.crear_unidad(
            'PUB-DET-001', 'Excavadora pública con detalle', self.admin
        )
        unidad_en_mantenimiento = self.crear_unidad(
            'PUB-DET-002', 'Excavadora en mantenimiento', self.admin,
            estado='Mantenimiento',
        )
        detalle_url = reverse(
            'inventario:maquinaria_detalle', args=[unidad.pk]
        )

        detalle = self.client.get(detalle_url)

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, unidad.maquinaria.nombre)
        self.assertContains(detalle, 'Equipo para trabajos de excavación.')
        self.assertContains(detalle, 'Iniciar sesión para solicitar')
        self.assertNotContains(detalle, 'id="sidebar"')
        self.assertNotContains(detalle, 'Cerrar sesión')
        self.assertNotContains(detalle, '$99000,00')
        self.assertEqual(
            self.client.get(
                reverse(
                    'inventario:maquinaria_detalle',
                    args=[unidad_en_mantenimiento.pk],
                )
            ).status_code,
            404,
        )

        solicitud_url = reverse(
            'alquileres:solicitud_registrar', args=[unidad.pk]
        )
        respuesta_solicitud = self.client.get(solicitud_url)

        self.assertEqual(respuesta_solicitud.status_code, 302)
        self.assertEqual(
            respuesta_solicitud.url.split('?')[0],
            reverse('cuentas:login'),
        )
        self.assertEqual(
            parse_qs(urlparse(respuesta_solicitud.url).query)['next'],
            [solicitud_url],
        )

    def test_tarifas_deben_aumentar_o_mantenerse_entre_planes(self):
        datos = {
            'categoria': self.categoria.pk,
            'codigo': 'TAR-001',
            'nombre': 'Maquinaria con tarifas válidas',
            'descripcion': '',
            'marca': '',
            'modelo': '',
            'costo_adquisicion': '10000',
            'tarifa_diaria': '500',
            'tarifa_semanal': '300',
            'tarifa_mensual': '200',
            'deposito_garantia': '0',
            'numero_serie': 'SERIE-TAR-001',
            'estado': 'Disponible',
            'horas_uso': '0',
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': 'Santo Domingo',
        }

        form = MaquinariaIntegralForm(data=datos)

        self.assertFalse(form.is_valid())
        self.assertIn('tarifa_semanal', form.errors)
        self.assertIn('tarifa_mensual', form.errors)
        self.assertEqual(Maquinaria.objects.filter(codigo='TAR-001').count(), 0)

    def test_tarifas_iguales_se_rechazan(self):
        datos = {
            'categoria': self.categoria.pk,
            'codigo': 'TAR-002',
            'nombre': 'Maquinaria con tarifas ordenadas',
            'descripcion': '',
            'marca': '',
            'modelo': '',
            'costo_adquisicion': '10000',
            'tarifa_diaria': '500',
            'tarifa_semanal': '500',
            'tarifa_mensual': '500',
            'deposito_garantia': '0',
            'numero_serie': 'SERIE-TAR-002',
            'estado': 'Disponible',
            'horas_uso': '0',
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': 'Santo Domingo',
        }

        form = MaquinariaIntegralForm(data=datos)

        self.assertFalse(form.is_valid())
        self.assertIn('tarifa_semanal', form.errors)
        self.assertIn('tarifa_mensual', form.errors)

    def test_tarifas_estrictamente_crecientes_se_aceptan(self):
        datos = {
            'categoria': self.categoria.pk,
            'codigo': 'TAR-003',
            'nombre': 'Maquinaria con tarifas crecientes',
            'descripcion': '',
            'marca': '',
            'modelo': '',
            'costo_adquisicion': '10000',
            'tarifa_diaria': '100',
            'tarifa_semanal': '200',
            'tarifa_mensual': '300',
            'deposito_garantia': '0',
            'numero_serie': 'SERIE-TAR-003',
            'estado': 'Disponible',
            'horas_uso': '0',
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': 'Santo Domingo',
        }

        form = MaquinariaIntegralForm(data=datos)

        self.assertTrue(form.is_valid(), form.errors)

    def test_administrador_puede_cambiar_estado_desde_formulario_integral(self):
        unidad = self.crear_unidad(
            'EST-004', 'Excavadora editable', self.admin,
        )
        datos = {
            'categoria': self.categoria.pk,
            'codigo': unidad.maquinaria.codigo,
            'nombre': unidad.maquinaria.nombre,
            'descripcion': unidad.maquinaria.descripcion,
            'marca': unidad.maquinaria.marca or '',
            'modelo': unidad.maquinaria.modelo or '',
            'costo_adquisicion': unidad.maquinaria.costo_adquisicion,
            'tarifa_diaria': unidad.maquinaria.tarifa_diaria,
            'tarifa_semanal': unidad.maquinaria.tarifa_semanal,
            'tarifa_mensual': unidad.maquinaria.tarifa_mensual,
            'deposito_garantia': unidad.maquinaria.deposito_garantia,
            'numero_serie': unidad.numero_serie,
            'estado': 'Mantenimiento',
            'horas_uso': unidad.horas_uso,
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': unidad.ubicacion_actual,
        }

        form = MaquinariaIntegralForm(data=datos, unidad=unidad)

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        unidad.refresh_from_db()
        self.assertEqual(unidad.estado, 'Mantenimiento')

    def test_panel_admin_muestra_solo_sus_unidades_disponibles_y_costo_interno(self):
        propia = self.crear_unidad('ADM-001', 'Excavadora propia', self.admin)
        self.crear_unidad('ADM-002', 'Excavadora ajena', self.cliente)
        historica = self.crear_unidad('ADM-005', 'Excavadora histórica', None)
        self.crear_unidad(
            'ADM-003', 'Excavadora alquilada', self.admin, estado='Alquilado'
        )
        self.crear_unidad(
            'ADM-006', 'Excavadora en mantenimiento', self.admin,
            estado='Mantenimiento',
        )
        self.crear_unidad(
            'ADM-007', 'Excavadora fuera de servicio', self.admin,
            estado='Baja',
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse('cuentas:dashboard'))

        self.assertContains(respuesta, propia.maquinaria.nombre)
        self.assertContains(respuesta, historica.maquinaria.nombre)
        self.assertContains(respuesta, '$99000,00')
        self.assertNotContains(respuesta, 'Excavadora ajena')
        self.assertNotContains(respuesta, 'Excavadora alquilada')
        self.assertNotContains(respuesta, 'Excavadora en mantenimiento')
        self.assertNotContains(respuesta, 'Excavadora fuera de servicio')

    def test_inventario_muestra_estados_a_admin_y_solo_disponibles_al_cliente(self):
        disponible = self.crear_unidad(
            'EST-001', 'Excavadora disponible', self.admin,
        )
        mantenimiento = self.crear_unidad(
            'EST-002', 'Excavadora en taller', self.admin,
            estado='Mantenimiento',
        )
        baja = self.crear_unidad(
            'EST-003', 'Excavadora retirada', self.admin,
            estado='Baja',
        )

        self.client.force_login(self.admin)
        respuesta_admin = self.client.get(reverse('inventario:maquinaria_lista'))

        self.assertContains(respuesta_admin, disponible.maquinaria.nombre)
        self.assertContains(respuesta_admin, mantenimiento.maquinaria.nombre)
        self.assertContains(respuesta_admin, 'En mantenimiento')
        self.assertContains(respuesta_admin, baja.maquinaria.nombre)
        self.assertContains(respuesta_admin, 'Fuera de servicio')

        self.client.force_login(self.cliente)
        respuesta_cliente = self.client.get(reverse('inventario:maquinaria_lista'))

        self.assertContains(respuesta_cliente, disponible.maquinaria.nombre)
        self.assertNotContains(respuesta_cliente, mantenimiento.maquinaria.nombre)
        self.assertNotContains(respuesta_cliente, baja.maquinaria.nombre)
        for unidad in (mantenimiento, baja):
            with self.subTest(estado=unidad.estado):
                self.assertEqual(
                    self.client.get(
                        reverse('inventario:maquinaria_detalle', args=[unidad.pk])
                    ).status_code,
                    404,
                )

    def test_cliente_ve_tarifas_y_deposito_pero_no_costo_adquisicion(self):
        unidad = self.crear_unidad('CLI-001', 'Excavadora para alquilar', self.admin)
        self.client.force_login(self.cliente)

        respuesta = self.client.get(
            reverse('inventario:maquinaria_detalle', args=[unidad.pk])
        )

        self.assertContains(respuesta, 'id="sidebar"')
        self.assertContains(respuesta, 'Cerrar sesión')
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
