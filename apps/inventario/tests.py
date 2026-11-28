from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.alquileres.models import SolicitudAlquiler
from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.form_utils import GroupedIntegerField
from apps.mantenimiento.models import Mantenimiento
from apps.marca.models import Marca
from apps.ventas.forms import PagoAlquilerForm
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler, ReembolsoDeposito
from .forms import MaquinariaIntegralForm
from .models import Categoria, Maquinaria, Unidad


class ConfirmacionesInventarioTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='confirmacion-admin@example.com', password='pass', rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='confirmacion-cliente@example.com', password='pass', rol=RolUsuario.CLIENTE,
        )
        self.categoria = Categoria.objects.create(nombre='Equipos')
        self.maquinaria = Maquinaria.objects.create(
            categoria=self.categoria, codigo='CONF-01', nombre='Excavadora',
            costo_adquisicion=1000, tarifa_diaria=100,
            tarifa_semanal=500, tarifa_mensual=1500,
        )
        self.unidad = Unidad.objects.create(maquinaria=self.maquinaria, numero_serie='SERIE-01')
        self.client.force_login(self.admin)

    def test_retiro_muestra_datos_y_cancelar_vuelve_al_origen(self):
        url = reverse('inventario:maquinaria_eliminar', args=[self.unidad.pk])
        for origen, destino in (
            ('', reverse('inventario:maquinaria_lista')),
            ('?origen=detalle', reverse('inventario:maquinaria_detalle', args=[self.unidad.pk])),
            ('?origen=editar', reverse('inventario:maquinaria_editar', args=[self.unidad.pk])),
            ('?origen=https://example.com', reverse('inventario:maquinaria_lista')),
        ):
            with self.subTest(origen=origen):
                respuesta = self.client.get(url + origen)
                for texto in ('Excavadora', 'CONF-01', 'SERIE-01', 'Equipos',
                              'podrá reactivarse', 'todas las unidades', 'Confirmar retiro', destino):
                    self.assertContains(respuesta, texto)
        self.maquinaria.refresh_from_db()
        self.assertTrue(self.maquinaria.activo)
        self.assertTrue(self.unidad.activo)
        for nombre in ('maquinaria_lista', 'maquinaria_detalle', 'maquinaria_editar'):
            args = [] if nombre == 'maquinaria_lista' else [self.unidad.pk]
            pagina = self.client.get(reverse('inventario:' + nombre, args=args))
            self.assertContains(pagina, url)
            self.assertNotContains(pagina, 'confirm(')
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_retiro_requiere_csrf_y_solo_post_modifica(self):
        url = reverse('inventario:maquinaria_eliminar', args=[self.unidad.pk])
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        respuesta = cliente.get(url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(cliente.post(url).status_code, 403)
        self.maquinaria.refresh_from_db()
        self.assertTrue(self.maquinaria.activo)
        token = cliente.cookies['csrftoken'].value
        self.assertRedirects(cliente.post(url, {'csrfmiddlewaretoken': token}),
                             reverse('inventario:maquinaria_lista'))
        self.maquinaria.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertFalse(self.maquinaria.activo)
        self.assertFalse(self.unidad.activo)

    def test_categoria_protegida_y_marca_exigen_confirmacion(self):
        categoria_url = reverse('inventario:categoria_eliminar', args=[self.categoria.pk])
        respuesta = self.client.get(categoria_url)
        self.assertContains(respuesta, 'No se puede eliminar esta categoría')
        self.assertNotContains(respuesta, 'Confirmar eliminación')
        categoria_vacia = Categoria.objects.create(nombre='Categoría vacía')
        respuesta = self.client.get(reverse('inventario:categoria_eliminar', args=[categoria_vacia.pk]))
        self.assertContains(respuesta, 'Confirmar eliminación')
        self.assertContains(respuesta, 'Esta acción no se puede deshacer')
        self.assertTrue(Categoria.objects.filter(pk=categoria_vacia.pk).exists())
        marca = Marca.objects.create(nombre='Sin uso')
        url = reverse('marca:marca_eliminar', args=[marca.pk])
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.get(url).status_code, 200)
        self.assertEqual(cliente.post(url).status_code, 403)
        self.assertTrue(Marca.objects.filter(pk=marca.pk).exists())


class CamposNumericosTests(TestCase):
    def test_campo_entero_acepta_comas_y_no_acepta_decimales(self):
        campo = GroupedIntegerField()

        self.assertEqual(campo.clean('3,450,000'), 3450000)
        self.assertEqual(campo.clean(''), 0)
        with self.assertRaises(ValidationError):
            campo.clean('12.50')

    def test_formularios_nuevos_no_precargan_cero(self):
        maquinaria = MaquinariaIntegralForm()
        pago = PagoAlquilerForm()

        for campo in ('costo_adquisicion', 'tarifa_diaria', 'tarifa_semanal',
                      'tarifa_mensual', 'deposito_garantia', 'horas_uso'):
            self.assertNotIn('value="0"', str(maquinaria[campo]))
        self.assertNotIn('value="0"', str(pago['monto']))

    def test_pago_permite_monto_vacio_y_lo_convierte_en_cero(self):
        formulario = PagoAlquilerForm(data={
            'concepto': 'renta',
            'monto': '',
            'metodo': 'efectivo',
            'referencia': '',
        })

        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertEqual(formulario.cleaned_data['monto'], 0)

    def test_formato_visible_usa_comas_y_no_muestra_centavos(self):
        plantilla = Template('{{ valor|entero_con_comas }}')
        self.assertEqual(
            plantilla.render(Context({'valor': 3450000})),
            '3,450,000',
        )


class DepositoManualInventarioTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-deposito@example.com', password='pass',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.categoria = Categoria.objects.create(nombre='Maquinaria')
        self.client.force_login(self.admin)
        self.datos = {
            'categoria': self.categoria.pk,
            'codigo': 'MAN-01',
            'nombre': 'Equipo',
            'costo_adquisicion': '100,000',
            'tarifa_diaria': '1,000',
            'tarifa_semanal': '5,000',
            'tarifa_mensual': '15,000',
            'deposito_garantia': '12,345',
            'numero_serie': 'MAN-SERIE',
            'estado': 'Disponible',
            'horas_uso': '0',
            'fecha_adquisicion': '2024-02-15',
            'ubicacion_actual': 'Almacén',
            'imagenes-TOTAL_FORMS': '0',
            'imagenes-INITIAL_FORMS': '0',
        }

    def test_admin_crea_y_edita_deposito_manualmente(self):
        crear = reverse('inventario:maquinaria_crear')
        self.assertContains(self.client.get(crear), 'name="deposito_garantia"')
        respuesta = self.client.post(crear, self.datos)
        self.assertEqual(respuesta.status_code, 302, respuesta.context and respuesta.context['form'].errors)
        maquinaria = Maquinaria.objects.get(codigo='MAN-01')
        self.assertEqual(maquinaria.deposito_garantia, 12345)

        unidad = maquinaria.unidades.get()
        self.assertEqual(unidad.fecha_adquisicion, date(2024, 2, 15))
        editar = reverse('inventario:maquinaria_editar', args=[unidad.pk])
        self.assertContains(self.client.get(editar), 'value="12345"')
        self.datos['deposito_garantia'] = '0'
        self.datos['costo_adquisicion'] = '200,000'
        respuesta = self.client.post(editar, self.datos)
        self.assertEqual(respuesta.status_code, 302, respuesta.context and respuesta.context['form'].errors)
        maquinaria.refresh_from_db()
        self.assertEqual(maquinaria.deposito_garantia, 0)
        unidad.refresh_from_db()
        self.assertEqual(unidad.fecha_adquisicion, date(2024, 2, 15))

    def test_deposito_negativo_no_se_acepta(self):
        self.datos['deposito_garantia'] = '-1'
        respuesta = self.client.post(reverse('inventario:maquinaria_crear'), self.datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context['form'].errors.get('deposito_garantia'))
        self.assertFalse(Maquinaria.objects.filter(codigo='MAN-01').exists())

    def test_solo_edicion_conserva_datos_registrados(self):
        maquinaria = Maquinaria.objects.create(
            categoria=self.categoria, codigo='EDIT-01', nombre='Equipo registrado',
            tarifa_diaria=1000, tarifa_semanal=5000, tarifa_mensual=15000,
            deposito_garantia=12345,
        )
        unidad = Unidad.objects.create(
            maquinaria=maquinaria, numero_serie='EDIT-SERIE',
            ubicacion_actual='Almacén', fecha_adquisicion=date(2024, 2, 15),
        )
        crear = self.client.get(reverse('inventario:maquinaria_crear'))
        editar = self.client.get(reverse('inventario:maquinaria_editar', args=[unidad.pk]))
        self.assertNotContains(crear, 'data-autosave-reset-initial')
        self.assertContains(editar, 'data-autosave-reset-initial')
        for texto in ('EDIT-01', 'Equipo registrado', 'EDIT-SERIE', 'Almacén', '12345', '2024-02-15'):
            self.assertContains(editar, texto)


class HistorialMaquinariaTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='historial-admin@example.com', password='pass',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='historial-tecnico@example.com', password='pass',
            rol=RolUsuario.TECNICO, first_name='Ana', last_name='Técnica',
            especialidad='Hidráulica',
        )
        self.cliente_historial = UsuarioPersonalizado.objects.create_user(
            email='cliente-historial@example.com', password='pass',
            rol=RolUsuario.CLIENTE, first_name='Mario', last_name='Cliente',
        )
        self.otro_cliente = UsuarioPersonalizado.objects.create_user(
            email='otro-cliente@example.com', password='pass',
            rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Historial')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='HIST-01', nombre='Excavadora histórica',
            tarifa_diaria=100, tarifa_semanal=500, tarifa_mensual=1500,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria, numero_serie='HIST-SERIE',
            ubicacion_actual='Almacén',
        )
        self.url = reverse('inventario:maquinaria_detalle', args=[self.unidad.pk])

        salida = timezone.make_aware(datetime(2026, 1, 10, 8))
        retorno = timezone.make_aware(datetime(2026, 1, 15, 16))
        self.solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente_historial,
            unidad=self.unidad,
            fecha_inicio=date(2026, 1, 10),
            fecha_fin=date(2026, 1, 14),
            plan='diario',
            cantidad=5,
            estado='Aprobada',
            fecha_revision=timezone.now(),
            revisado_por=self.admin,
            fecha_salida=salida,
            entregado_por=self.admin,
            fecha_retorno=retorno,
            recibido_por=self.admin,
            dias_atraso=1,
        )
        presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=self.solicitud,
            importe_renta=100,
            deposito_garantia=20,
            mora_total=10,
            tarifa_periodo=100,
        )
        for concepto, monto in (('renta', 100), ('deposito', 20), ('mora', 10)):
            PagoAlquiler.objects.create(
                presupuesto=presupuesto,
                concepto=concepto,
                monto=monto,
                metodo='efectivo',
                registrado_por=self.admin,
            )
        ReembolsoDeposito.objects.create(
            presupuesto=presupuesto,
            monto=5,
            metodo='efectivo',
            registrado_por=self.admin,
        )
        Mantenimiento.objects.create(
            unidad=self.unidad,
            fecha=date(2026, 2, 5),
            tipo='Correctivo',
            descripcion='Cambio de manguera hidráulica',
            estado='finalizada',
            fecha_fin=date(2026, 2, 5),
            costo=300,
            tecnico=self.tecnico,
            registrado_por=self.admin,
        )
        Mantenimiento.objects.create(
            unidad=self.unidad,
            fecha=date(2026, 3, 2),
            tipo='Preventivo',
            descripcion='Revisión general',
            estado='pendiente',
            costo=200,
            tecnico=self.tecnico,
            registrado_por=self.admin,
        )

    def test_admin_ve_historial_financiero_y_mantenimientos_centralizados(self):
        self.client.force_login(self.admin)

        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, 'Historial de solicitudes y alquileres')
        self.assertContains(respuesta, 'Mario Cliente')
        self.assertContains(respuesta, '10/01/2026 - 14/01/2026')
        self.assertContains(respuesta, 'RD$125')
        self.assertContains(respuesta, 'Recaudación neta acumulada')
        self.assertContains(respuesta, 'Historial de mantenimiento y reparaciones')
        self.assertContains(respuesta, 'Ana Técnica')
        self.assertContains(respuesta, 'Cambio de manguera hidráulica')
        self.assertContains(respuesta, 'RD$500')
        self.assertEqual(respuesta.context['total_recaudado_maquinaria'], 125)
        self.assertEqual(respuesta.context['total_invertido_mantenimiento'], 500)

    def test_historial_financiero_no_se_expone_a_clientes(self):
        self.client.force_login(self.otro_cliente)

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, 'Historial de solicitudes y alquileres')
        self.assertNotContains(respuesta, self.cliente_historial.email)
        self.assertNotContains(respuesta, 'Historial de mantenimiento y reparaciones')

    def test_tecnico_ve_mantenimiento_sin_datos_financieros_de_clientes(self):
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, 'Historial de solicitudes y alquileres')
        self.assertNotContains(respuesta, self.cliente_historial.email)
        self.assertContains(respuesta, 'Historial de mantenimiento y reparaciones')
        self.assertContains(respuesta, 'RD$500')
