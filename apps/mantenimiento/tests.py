from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad


class MantenimientoListaEstadoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-estados@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        categoria = Categoria.objects.create(nombre='Equipos de prueba')
        cls.unidades = {}
        for indice, estado in enumerate(
            ('Disponible', 'Alquilado', 'Mantenimiento', 'Baja'), start=1,
        ):
            maquinaria = Maquinaria.objects.create(
                categoria=categoria,
                codigo=f'MAN-{indice:03}',
                nombre=f'Equipo {estado}',
                costo_adquisicion=1000,
                tarifa_diaria=100,
                tarifa_semanal=700,
                tarifa_mensual=3000,
            )
            cls.unidades[estado] = Unidad.objects.create(
                maquinaria=maquinaria,
                numero_serie=f'SERIE-MAN-{indice:03}',
                estado=estado,
                ubicacion_actual='Taller',
            )

    def test_mantenimiento_refleja_estados_y_solo_ofrece_registro_aplicable(self):
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(reverse('mantenimiento:mantenimiento_lista'))

        self.assertEqual(respuesta.status_code, 200)
        for estado in self.unidades:
            with self.subTest(estado=estado):
                self.assertContains(
                    respuesta,
                    self.unidades[estado].maquinaria.nombre,
                )
        self.assertContains(respuesta, 'Fuera de servicio')
        self.assertContains(
            respuesta,
            f"?unidad={self.unidades['Disponible'].pk}",
        )
        self.assertContains(
            respuesta,
            f"?unidad={self.unidades['Mantenimiento'].pk}",
        )
        self.assertNotContains(
            respuesta,
            f"?unidad={self.unidades['Alquilado'].pk}",
        )
        self.assertNotContains(
            respuesta,
            f"?unidad={self.unidades['Baja'].pk}",
        )
