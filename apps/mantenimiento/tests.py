from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import PermissionDenied, ValidationError

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from .forms import MantenimientoForm
from .models import Mantenimiento


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


class AsignacionMantenimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-asigna@example.com', first_name='Ana', last_name='Administradora', rol=RolUsuario.ADMINISTRADOR,
        )
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-asigna@example.com', first_name='Tomás', rol=RolUsuario.TECNICO, especialidad='Hidráulica',
        )
        cls.electricista = UsuarioPersonalizado.objects.create_user(
            email='electricista@example.com', rol=RolUsuario.TECNICO, especialidad='Electricidad',
        )
        cls.inactivo = UsuarioPersonalizado.objects.create_user(
            email='inactivo@example.com', rol=RolUsuario.TECNICO, especialidad='Hidráulica', is_active=False,
        )
        cls.no_disponible = UsuarioPersonalizado.objects.create_user(
            email='ocupado@example.com', rol=RolUsuario.TECNICO, especialidad='Hidráulica', disponible=False,
        )
        cls.cliente = UsuarioPersonalizado.objects.create_user(email='cliente-asigna@example.com')
        categoria = Categoria.objects.create(nombre='Asignación')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='ASIG-001', nombre='Excavadora', costo_adquisicion=1000,
            tarifa_diaria=100, tarifa_semanal=700, tarifa_mensual=3000,
        )
        cls.unidad = Unidad.objects.create(maquinaria=maquinaria, numero_serie='ASIG-001', estado='Disponible')

    def setUp(self):
        self.url = reverse('mantenimiento:mantenimiento_registrar')
        self.datos = {
            'unidad': self.unidad.pk, 'fecha': '2026-11-14', 'tipo': 'Preventivo',
            'descripcion': 'Revisión hidráulica', 'costo': '150.00',
            'especialidad': 'Hidráulica', 'tecnico_responsable': self.tecnico.pk,
        }

    def test_administrador_ve_registrado_por_y_solo_tecnicos_elegibles(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get(self.url + f'?unidad={self.unidad.pk}')
        self.assertContains(respuesta, 'Registrado por: Ana Administradora')
        self.assertContains(respuesta, 'Filtrar por especialidad')
        self.assertEqual(respuesta.context['form']['unidad'].value(), str(self.unidad.pk))
        opciones = respuesta.context['form'].fields['tecnico_responsable'].queryset
        self.assertSetEqual(set(opciones.values_list('pk', flat=True)), {self.tecnico.pk, self.electricista.pk})

    def test_administrador_guarda_responsable_y_autoria_separados(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(self.url, {**self.datos, 'registrado_por': self.cliente.pk})
        self.assertRedirects(respuesta, reverse('mantenimiento:mantenimiento_historial', args=[self.unidad.pk]))
        mantenimiento = Mantenimiento.objects.get()
        self.assertEqual(mantenimiento.tecnico, self.tecnico)
        self.assertEqual(mantenimiento.registrado_por, self.admin)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Mantenimiento')
        historial = self.client.get(respuesta.url)
        self.assertContains(historial, 'Ana Administradora')
        self.assertContains(historial, 'Tomás')

    def test_servidor_rechaza_responsable_invalido_o_que_no_coincide(self):
        self.client.force_login(self.admin)
        for responsable in (self.inactivo.pk, self.no_disponible.pk, self.admin.pk, self.cliente.pk,
                            self.electricista.pk, 999999, ''):
            with self.subTest(responsable=responsable):
                respuesta = self.client.post(self.url, {**self.datos, 'tecnico_responsable': responsable})
                self.assertEqual(respuesta.status_code, 200)
                self.assertIn('tecnico_responsable', respuesta.context['form'].errors)
                self.assertFalse(Mantenimiento.objects.exists())
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')

    def test_filtro_vacio_y_sin_coincidencias_conservan_datos_del_formulario(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post(self.url, {**self.datos, 'especialidad': '', 'filtrar': '1'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form']['descripcion'].value(), self.datos['descripcion'])
        self.assertEqual(respuesta.context['form'].fields['tecnico_responsable'].queryset.count(), 2)
        respuesta = self.client.post(self.url, {**self.datos, 'especialidad': 'Mecánica', 'filtrar': '1'})
        self.assertTrue(respuesta.context['form'].sin_tecnicos)
        self.assertContains(respuesta, 'No hay técnicos activos y disponibles para esta especialidad.')
        self.assertFalse(Mantenimiento.objects.exists())

    def test_guardado_revalida_cambios_despues_de_validar_formulario(self):
        for cambios in ({'is_active': False}, {'disponible': False}, {'rol': RolUsuario.CLIENTE},
                        {'especialidad': 'Electricidad'}):
            with self.subTest(cambios=cambios):
                form = MantenimientoForm(self.datos, usuario=self.admin)
                self.assertTrue(form.is_valid(), form.errors)
                UsuarioPersonalizado.objects.filter(pk=self.tecnico.pk).update(**cambios)
                with self.assertRaises(ValidationError):
                    form.save()
                self.assertFalse(Mantenimiento.objects.exists())
                self.unidad.refresh_from_db()
                self.assertEqual(self.unidad.estado, 'Disponible')
                UsuarioPersonalizado.objects.filter(pk=self.tecnico.pk).update(
                    is_active=True, disponible=True, rol=RolUsuario.TECNICO, especialidad='Hidráulica',
                )

    def test_tecnico_se_autoasigna_aunque_intenten_enviar_otro_responsable(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'Técnico responsable: Tomás')
        self.assertNotIn('tecnico_responsable', respuesta.context['form'].fields)
        self.assertNotIn('especialidad', respuesta.context['form'].fields)
        respuesta = self.client.post(self.url, {**self.datos, 'tecnico_responsable': self.electricista.pk})
        self.assertEqual(respuesta.status_code, 302)
        mantenimiento = Mantenimiento.objects.get()
        self.assertEqual(mantenimiento.tecnico, self.tecnico)
        self.assertEqual(mantenimiento.registrado_por, self.tecnico)

    def test_no_disponibilidad_solo_limita_asignacion_del_administrador(self):
        self.client.force_login(self.no_disponible)
        respuesta = self.client.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Mantenimiento.objects.get().tecnico, self.no_disponible)

    def test_cliente_no_registra_y_administrador_inactivo_no_guarda(self):
        self.client.force_login(self.cliente)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos).status_code, 403)
        form = MantenimientoForm(self.datos, usuario=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        UsuarioPersonalizado.objects.filter(pk=self.admin.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            form.save()
        self.assertFalse(Mantenimiento.objects.exists())

    def test_unidad_que_deja_de_estar_disponible_no_se_modifica(self):
        form = MantenimientoForm(self.datos, usuario=self.admin)
        self.assertTrue(form.is_valid(), form.errors)
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Alquilado')
        with self.assertRaises(ValidationError):
            form.save()
        self.assertFalse(Mantenimiento.objects.exists())
