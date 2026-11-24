from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import Client, TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.form_utils import GroupedIntegerField
from apps.marca.models import Marca
from apps.ventas.forms import PagoAlquilerForm
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
                      'tarifa_mensual', 'horas_uso'):
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
