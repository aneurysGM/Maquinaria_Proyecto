from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PresupuestoAlquiler
from .models import SolicitudAlquiler


class SolicitudesAlquilerTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-alquiler@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        categoria, _ = Categoria.objects.get_or_create(nombre='Excavadoras')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='ALQ-001',
            nombre='Excavadora para alquiler',
            descripcion='Equipo para obras.',
            costo_adquisicion=99000,
            tarifa_diaria=750,
            tarifa_semanal=4500,
            tarifa_mensual=15000,
            deposito_garantia=3000,
            registrada_por=self.admin,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SERIE-ALQ-001',
            ubicacion_actual='Santo Domingo',
            estado='Disponible',
        )

    def test_cliente_puede_enviar_solicitud_y_verla_en_su_bandeja(self):
        self.client.force_login(self.cliente)
        inicio = timezone.localdate() + timedelta(days=1)

        respuesta = self.client.post(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
            {
                'fecha_inicio': inicio.isoformat(),
                'plan': 'semanal',
                'cantidad': '2',
                'comentario': 'Obra de prueba',
            },
            follow=True,
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)
        solicitud = SolicitudAlquiler.objects.get()
        self.assertEqual(solicitud.cliente, self.cliente)
        self.assertEqual(solicitud.unidad, self.unidad)
        self.assertEqual(solicitud.fecha_fin, inicio + timedelta(days=13))
        self.assertEqual(solicitud.plan, 'semanal')
        self.assertEqual(solicitud.cantidad, 2)
        self.assertEqual(solicitud.presupuesto.tarifa_periodo, 4500)
        self.assertEqual(solicitud.presupuesto.importe_renta, 9000)
        self.assertEqual(solicitud.presupuesto.deposito_garantia, 3000)
        self.assertEqual(solicitud.presupuesto.importe_total, 12000)
        self.assertContains(respuesta, 'Obra de prueba')
        self.assertContains(respuesta, 'Pendiente')
        self.assertContains(respuesta, 'Presupuesto')
        self.assertContains(
            respuesta,
            f'href="{reverse("inventario:maquinaria_lista")}"',
        )
        self.assertContains(respuesta, 'Volver a maquinarias')

    def test_cliente_puede_ir_a_maquinarias_desde_sus_solicitudes(self):
        self.client.force_login(self.cliente)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertContains(respuesta, 'Ver maquinaria disponible')
        self.assertContains(
            respuesta,
            f'href="{reverse("inventario:maquinaria_lista")}"',
        )

    def test_tecnico_no_puede_consultar_bandeja_de_solicitudes(self):
        self.client.force_login(self.tecnico)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertEqual(respuesta.status_code, 403)

    def test_administrador_puede_revisar_solicitudes_pendientes(self):
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            fecha_inicio=timezone.localdate() + timedelta(days=1),
            fecha_fin=timezone.localdate() + timedelta(days=2),
        )
        self.client.force_login(self.admin)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertContains(respuesta, 'Solicitudes recibidas', status_code=200)
        self.assertContains(respuesta, f'name="decision" value="Aprobada"')
        self.assertContains(respuesta, f'action="/alquileres/solicitudes/resolver/{solicitud.pk}/"')

    def test_warning_y_mora_comienzan_desde_el_primer_dia_de_atraso(self):
        hoy = timezone.localdate()
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            fecha_inicio=hoy - timedelta(days=5),
            fecha_fin=hoy - timedelta(days=1),
            plan='diario',
            cantidad=1,
            estado='Aprobada',
            fecha_salida=timezone.now() - timedelta(days=5),
            entregado_por=self.admin,
        )
        self.unidad.estado = 'Alquilado'
        self.unidad.save(update_fields=['estado'])
        PresupuestoAlquiler.objects.create(
            solicitud=solicitud,
            tarifa_periodo=750,
            importe_renta=750,
            deposito_garantia=3000,
        )
        self.client.force_login(self.cliente)

        respuesta = self.client.get(reverse('alquileres:solicitud_lista'))

        self.assertContains(respuesta, '1 día(s) de atraso')
        self.assertContains(respuesta, 'Mora estimada')
        self.assertContains(respuesta, '$75')

    def test_segunda_devolucion_con_mas_de_tres_dias_suspende_por_seis_meses(self):
        hoy = timezone.localdate()

        def crear_retorno_pendiente(codigo):
            solicitud = SolicitudAlquiler.objects.create(
                cliente=self.cliente,
                unidad=self.unidad,
                fecha_inicio=hoy - timedelta(days=10),
                fecha_fin=hoy - timedelta(days=4),
                plan='diario',
                cantidad=1,
                estado='Aprobada',
                fecha_salida=timezone.now() - timedelta(days=5),
                entregado_por=self.admin,
            )
            PresupuestoAlquiler.objects.create(
                solicitud=solicitud,
                tarifa_periodo=750,
                importe_renta=750,
                deposito_garantia=3000,
            )
            self.unidad.estado = 'Alquilado'
            self.unidad.save(update_fields=['estado'])
            return solicitud

        primera = crear_retorno_pendiente('primera')
        self.client.force_login(self.admin)
        primera_respuesta = self.client.post(
            reverse('alquileres:solicitud_retorno', args=[primera.pk]),
            {'horas_uso_actualizadas': '10', 'observaciones_retorno': ''},
        )
        primera.refresh_from_db()
        self.assertRedirects(
            primera_respuesta,
            reverse('alquileres:solicitud_lista'),
        )
        self.assertEqual(primera.dias_atraso, 4)
        self.assertEqual(primera.presupuesto.mora_total, 375)
        self.assertTrue(self.cliente.is_active)

        segunda = crear_retorno_pendiente('segunda')
        segunda_respuesta = self.client.post(
            reverse('alquileres:solicitud_retorno', args=[segunda.pk]),
            {'horas_uso_actualizadas': '12', 'observaciones_retorno': ''},
        )
        self.cliente.refresh_from_db()

        self.assertRedirects(
            segunda_respuesta,
            reverse('alquileres:solicitud_lista'),
        )
        self.assertFalse(self.cliente.is_active)
        self.assertIsNotNone(self.cliente.suspension_hasta)
        self.assertGreater(self.cliente.suspension_hasta, hoy)
