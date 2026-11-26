from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import DireccionCliente, RolUsuario, UsuarioPersonalizado


class FormulariosEdicionConfiguracionTests(TestCase):
    def setUp(self):
        self.usuario = UsuarioPersonalizado.objects.create_user(
            email='cliente@example.com',
            password='PruebaSegura123!',
            first_name='María',
            last_name='Gómez',
            telefono='809-555-0101',
            rol=RolUsuario.CLIENTE,
        )
        self.client.force_login(self.usuario)

    def test_perfil_muestra_datos_guardados_y_conserva_valores_iniciales(self):
        respuesta = self.client.get(reverse('configuraciones:mi_perfil'))

        self.assertContains(respuesta, 'data-autosave-reset-initial')
        self.assertContains(respuesta, 'value="María"')
        self.assertContains(respuesta, 'value="Gómez"')
        self.assertContains(respuesta, 'value="809-555-0101"')

    def test_edicion_de_direccion_muestra_datos_guardados(self):
        direccion = DireccionCliente.objects.create(
            cliente=self.usuario,
            nombre='Oficina',
            direccion='Calle Principal 10, Santo Domingo',
            referencia='Frente al parque',
        )

        respuesta = self.client.get(
            reverse('configuraciones:direccion_editar', args=[direccion.pk])
        )

        self.assertContains(respuesta, 'data-autosave-reset-initial')
        self.assertContains(respuesta, 'value="Oficina"')
        self.assertContains(respuesta, 'Calle Principal 10, Santo Domingo')
        self.assertContains(respuesta, 'Frente al parque')

    def test_nueva_direccion_no_se_trata_como_formulario_de_edicion(self):
        respuesta = self.client.get(reverse('configuraciones:direccion_agregar'))

        self.assertNotContains(respuesta, 'data-autosave-reset-initial')
