from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado


class ConfiguracionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {
            rol: UsuarioPersonalizado.objects.create_user(
                email=f'{rol.lower()}-config@example.com',
                password='ClaveActual!2026',
                rol=rol,
            )
            for rol in (
                RolUsuario.ADMINISTRADOR,
                RolUsuario.CLIENTE,
                RolUsuario.TECNICO,
            )
        }

    def test_roles_admitidos_pueden_abrir_configuraciones(self):
        for rol, usuario in self.usuarios.items():
            with self.subTest(rol=rol):
                self.client.force_login(usuario)
                respuesta = self.client.get(reverse('configuraciones:indice'))
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, 'Cambiar contraseña')

    def test_cambio_requiere_contrasena_actual_y_confirmacion(self):
        usuario = self.usuarios[RolUsuario.TECNICO]
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse('configuraciones:cambiar_contrasena'),
            {
                'old_password': 'ClaveActual!2026',
                'new_password1': 'ClaveNueva!2026',
                'new_password2': 'ClaveNueva!2026',
            },
            follow=True,
        )

        self.assertRedirects(respuesta, reverse('configuraciones:indice'))
        self.assertContains(respuesta, 'Tu contraseña se cambió correctamente.')
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('ClaveNueva!2026'))

    def test_cambio_no_acepta_contrasena_actual_incorrecta(self):
        usuario = self.usuarios[RolUsuario.CLIENTE]
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse('configuraciones:cambiar_contrasena'),
            {
                'old_password': 'incorrecta',
                'new_password1': 'ClaveNueva!2026',
                'new_password2': 'ClaveNueva!2026',
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('ClaveActual!2026'))

    def test_cambio_exige_confirmar_la_nueva_contrasena(self):
        usuario = self.usuarios[RolUsuario.ADMINISTRADOR]
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse('configuraciones:cambiar_contrasena'),
            {
                'old_password': 'ClaveActual!2026',
                'new_password1': 'ClaveNueva!2026',
                'new_password2': 'OtraClave!2026',
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('ClaveActual!2026'))

    def test_acceso_sin_sesion_redirige_al_login(self):
        respuesta = self.client.get(reverse('configuraciones:indice'))

        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={reverse('configuraciones:indice')}",
        )
