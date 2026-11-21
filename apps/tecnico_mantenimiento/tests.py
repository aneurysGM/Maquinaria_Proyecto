from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.mantenimiento.models import Mantenimiento


class GestionTecnicosTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-gestion@example.com', password='pass', rol=RolUsuario.ADMINISTRADOR,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-gestion@example.com', password='pass', rol=RolUsuario.TECNICO,
        )
        self.client.force_login(self.admin)

    def test_activar_inactivar_eliminar_y_permisos(self):
        estado = reverse('tecnico_mantenimiento:cambiar_estado', args=[self.tecnico.pk])
        eliminar = reverse('tecnico_mantenimiento:eliminar', args=[self.tecnico.pk])
        self.assertEqual(self.client.get(estado).status_code, 405)
        self.client.post(estado)
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_active)
        self.client.post(estado)
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.is_active)
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(eliminar).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(eliminar)
        self.assertFalse(UsuarioPersonalizado.objects.filter(pk=self.tecnico.pk).exists())

    def test_historial_protegido_y_orden_abierta(self):
        categoria = Categoria.objects.create(nombre='Taller')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='TEC-01', nombre='Equipo',
            costo_adquisicion=1000, tarifa_diaria=100,
            tarifa_semanal=500, tarifa_mensual=1500,
        )
        unidad = Unidad.objects.create(maquinaria=maquinaria, numero_serie='TEC-01')
        orden = Mantenimiento.objects.create(
            unidad=unidad, fecha=timezone.localdate(), tipo='Correctivo',
            descripcion='Prueba', costo=0, tecnico=self.tecnico,
        )
        estado = reverse('tecnico_mantenimiento:cambiar_estado', args=[self.tecnico.pk])
        self.client.post(estado)
        self.tecnico.refresh_from_db()
        self.assertTrue(self.tecnico.is_active)
        self.client.post(reverse('tecnico_mantenimiento:eliminar', args=[self.tecnico.pk]))
        self.assertTrue(UsuarioPersonalizado.objects.filter(pk=self.tecnico.pk).exists())
        orden.estado = 'finalizada'
        orden.fecha_fin = timezone.localdate()
        orden.save(update_fields=['estado', 'fecha_fin'])
        self.client.post(estado)
        self.tecnico.refresh_from_db()
        self.assertFalse(self.tecnico.is_active)
