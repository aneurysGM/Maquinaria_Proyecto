from decimal import Decimal

from django import forms
from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.forms import MaquinariaIntegralForm
from apps.inventario.models import Categoria, Maquinaria
from .models import Marca


class MarcaManagementTests(TestCase):
    def setUp(self):
        self.administrador = UsuarioPersonalizado.objects.create_user(
            email='admin-marcas@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-marcas@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.categoria = Categoria.objects.create(nombre='Maquinaria con marcas')
        self.client.force_login(self.administrador)

    def crear_maquinaria(self, marca=None):
        return Maquinaria.objects.create(
            categoria=self.categoria,
            codigo='MARCA-01',
            nombre='Equipo con marca',
            marca=marca,
            costo_adquisicion=Decimal('1000.00'),
            tarifa_diaria=Decimal('100.00'),
            tarifa_semanal=Decimal('500.00'),
            tarifa_mensual=Decimal('1500.00'),
        )

    def test_administrador_puede_crear_editar_y_borrar_marca_sin_uso(self):
        respuesta = self.client.post(
            reverse('marca:marca_crear'),
            {'nombre': ' Caterpillar '},
        )
        self.assertRedirects(respuesta, reverse('marca:marca_lista'))
        marca = Marca.objects.get()
        self.assertEqual(marca.nombre, 'Caterpillar')

        respuesta = self.client.post(
            reverse('marca:marca_editar', args=[marca.pk]),
            {'nombre': 'Komatsu'},
        )
        self.assertRedirects(respuesta, reverse('marca:marca_lista'))
        marca.refresh_from_db()
        self.assertEqual(marca.nombre, 'Komatsu')

        respuesta = self.client.post(
            reverse('marca:marca_eliminar', args=[marca.pk]),
        )
        self.assertRedirects(respuesta, reverse('marca:marca_lista'))
        self.assertFalse(Marca.objects.filter(pk=marca.pk).exists())

    def test_marca_asignada_no_se_puede_borrar(self):
        marca = Marca.objects.create(nombre='Caterpillar')
        maquinaria = self.crear_maquinaria(marca=marca)

        respuesta = self.client.post(
            reverse('marca:marca_eliminar', args=[marca.pk]),
        )

        self.assertRedirects(respuesta, reverse('marca:marca_lista'))
        self.assertTrue(Marca.objects.filter(pk=marca.pk).exists())
        maquinaria.refresh_from_db()
        self.assertEqual(maquinaria.marca, marca)

    def test_confirmacion_de_marca_y_proteccion_de_asociadas(self):
        marca = Marca.objects.create(nombre='Marca de prueba')
        url = reverse('marca:marca_eliminar', args=[marca.pk])
        lista = self.client.get(reverse('marca:marca_lista'))
        self.assertContains(lista, f'href="{url}"')
        self.assertNotContains(lista, 'confirm(')
        respuesta = self.client.get(url)
        self.assertContains(respuesta, marca.nombre)
        self.assertContains(respuesta, 'Esta acción no se puede deshacer')
        self.assertContains(respuesta, 'Confirmar eliminación')
        self.assertContains(respuesta, reverse('marca:marca_lista'))
        self.assertTrue(Marca.objects.filter(pk=marca.pk).exists())
        self.crear_maquinaria(marca=marca)
        respuesta = self.client.get(url)
        self.assertContains(respuesta, 'No se puede borrar una marca asignada')
        self.assertNotContains(respuesta, 'Confirmar eliminación')
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_formulario_de_maquinaria_ofrece_select_con_marcas_registradas(self):
        marca = Marca.objects.create(nombre='Komatsu')

        form = MaquinariaIntegralForm()
        respuesta = self.client.get(reverse('inventario:maquinaria_crear'))

        self.assertIsInstance(form.fields['marca'].widget, forms.Select)
        self.assertFalse(form.fields['marca'].required)
        self.assertEqual(list(form.fields['marca'].queryset), [marca])
        self.assertEqual(respuesta.status_code, 200)
        self.assertRegex(respuesta.content.decode(), r'<select[^>]*name="marca"')
        self.assertContains(respuesta, 'Komatsu')

    def test_gestion_de_marcas_solo_esta_disponible_para_administradores(self):
        respuesta_admin = self.client.get(reverse('inventario:maquinaria_lista'))
        self.assertContains(respuesta_admin, 'Gestionar Categorías')
        self.assertContains(respuesta_admin, 'Gestionar Marcas')

        respuesta_dashboard = self.client.get(reverse('cuentas:dashboard'))
        self.assertNotContains(respuesta_dashboard, 'Gestionar Marcas')

        self.client.force_login(self.cliente)

        respuesta = self.client.get(reverse('marca:marca_lista'))

        self.assertEqual(respuesta.status_code, 403)
