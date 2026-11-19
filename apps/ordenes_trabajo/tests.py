from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.mantenimiento.models import Mantenimiento
from .models import ComentarioOrden, ConsumoRepuesto, Repuesto, SolicitudRepuesto


class OrdenTrabajoTests(TestCase):
    def setUp(self):
        self.administrador = UsuarioPersonalizado.objects.create_user(
            email='admin-ordenes@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-ordenes@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        self.otro_tecnico = UsuarioPersonalizado.objects.create_user(
            email='otro-tecnico-ordenes@example.com',
            password='test-password',
            rol=RolUsuario.TECNICO,
        )
        categoria = Categoria.objects.create(nombre='Equipos de prueba')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='OT-001',
            nombre='Excavadora de prueba',
            costo_adquisicion=Decimal('1000.00'),
            tarifa_diaria=Decimal('100.00'),
            tarifa_semanal=Decimal('500.00'),
            tarifa_mensual=Decimal('1500.00'),
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SERIE-OT-001',
            estado='Mantenimiento',
            horas_uso=Decimal('100.0'),
            intervalo_mantenimiento_horas=Decimal('50.0'),
            proximo_mantenimiento_horas=Decimal('150.0'),
        )
        self.orden = Mantenimiento.objects.create(
            unidad=self.unidad,
            fecha=date.today(),
            tipo='Correctivo',
            descripcion='Falla de prueba',
            estado='pendiente',
            costo=Decimal('0.00'),
            tecnico=self.tecnico,
            registrado_por=self.administrador,
        )

    def test_bandeja_y_detalle_solo_muestran_ordenes_asignadas_al_tecnico(self):
        self.client.force_login(self.otro_tecnico)
        respuesta = self.client.get(reverse('ordenes_trabajo:lista'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'SERIE-OT-001')

        respuesta = self.client.get(
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        self.assertEqual(respuesta.status_code, 404)

        self.client.force_login(self.tecnico)
        respuesta = self.client.get(
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Checklist de inspección')

        respuesta = self.client.get(
            reverse('mantenimiento:mantenimiento_historial', args=[self.unidad.pk]),
        )
        self.assertEqual(respuesta.status_code, 200)
        respuesta = self.client.get(
            reverse('mantenimiento:unidad_qr', args=[self.unidad.pk]),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'image/svg+xml')

        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('ordenes_trabajo:lista'))
        self.assertContains(respuesta, 'SERIE-OT-001')

    def test_finalizacion_exige_checklist_y_programa_proximo_servicio(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:actualizar', args=[self.orden.pk]),
            {
                'estado': 'reparacion',
                'horas_trabajo': '2.5',
                'horometro': '120.0',
                'observaciones': 'Se corrigió la fuga hidráulica.',
            },
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )

        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'reparacion')
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.horas_uso, Decimal('120.0'))
        self.assertEqual(self.orden.horas_mano_obra_total, Decimal('2.5'))

        respuesta = self.client.post(
            reverse('ordenes_trabajo:finalizar', args=[self.orden.pk]),
            {'observaciones': 'Equipo probado y operativo.'},
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        self.orden.refresh_from_db()
        self.assertIsNone(self.orden.fecha_fin)

        checklist = {
            'resultado_fluidos': 'correcto',
            'observacion_fluidos': '',
            'resultado_hidraulico': 'correcto',
            'observacion_hidraulico': '',
            'resultado_rodaje': 'no_aplica',
            'observacion_rodaje': '',
            'resultado_electrico': 'correcto',
            'observacion_electrico': '',
        }
        respuesta = self.client.post(
            reverse('ordenes_trabajo:checklist', args=[self.orden.pk]),
            checklist,
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        respuesta = self.client.post(
            reverse('ordenes_trabajo:finalizar', args=[self.orden.pk]),
            {'observaciones': 'Equipo probado y operativo.'},
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'finalizada')
        self.assertIsNotNone(self.orden.fecha_fin)
        self.assertEqual(
            self.unidad.proximo_mantenimiento_horas,
            Decimal('170.0'),
        )

    def test_horometro_no_puede_disminuir(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:actualizar', args=[self.orden.pk]),
            {
                'estado': 'diagnostico',
                'horas_trabajo': '1.0',
                'horometro': '99.0',
                'observaciones': 'Revisión de la falla.',
            },
            follow=True,
        )
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.horas_uso, Decimal('100.0'))
        self.assertEqual(self.orden.registros_trabajo.count(), 0)
        self.assertContains(respuesta, 'no puede ser menor')

    def test_tecnico_puede_agregar_comentario_a_la_orden(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:comentar', args=[self.orden.pk]),
            {'comentario': 'Se detectó desgaste en la manguera hidráulica.'},
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        comentario = ComentarioOrden.objects.get(mantenimiento=self.orden)
        self.assertEqual(comentario.autor, self.tecnico)
        self.assertEqual(
            comentario.comentario,
            'Se detectó desgaste en la manguera hidráulica.',
        )

    def test_administrador_solo_consulta_el_detalle_de_la_orden(self):
        self.client.force_login(self.administrador)
        respuesta = self.client.get(
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Esta vista es de solo lectura')
        self.assertContains(respuesta, 'Técnico asignado')
        self.assertNotContains(respuesta, 'Guardar avance')
        self.assertNotContains(respuesta, 'Enviar solicitud')
        self.assertNotContains(respuesta, 'Marcar como finalizada')

        respuesta = self.client.post(
            reverse('ordenes_trabajo:actualizar', args=[self.orden.pk]),
            {
                'estado': 'reparacion',
                'horas_trabajo': '2.0',
                'horometro': '110.0',
                'observaciones': 'El administrador no debe registrar avances.',
            },
        )
        self.assertEqual(respuesta.status_code, 403)
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'pendiente')
        self.assertEqual(self.orden.registros_trabajo.count(), 0)
        self.assertEqual(self.unidad.horas_uso, Decimal('100.0'))

        acciones_tecnicas = (
            'ordenes_trabajo:comentar',
            'ordenes_trabajo:checklist',
            'ordenes_trabajo:finalizar',
            'ordenes_trabajo:solicitar_repuestos',
            'ordenes_trabajo:consumir_repuesto',
        )
        for nombre_ruta in acciones_tecnicas:
            with self.subTest(ruta=nombre_ruta):
                respuesta = self.client.post(
                    reverse(nombre_ruta, args=[self.orden.pk]),
                )
                self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(ComentarioOrden.objects.count(), 0)
        self.assertEqual(SolicitudRepuesto.objects.count(), 0)

    def test_tecnico_puede_consultar_inventario_sin_acciones_administrativas(self):
        Repuesto.objects.create(
            codigo='REP-T-001',
            nombre='Filtro de prueba',
            existencia=Decimal('4.00'),
        )
        self.client.force_login(self.tecnico)
        respuesta = self.client.get(reverse('Repuestos_Inventario:lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'REP-T-001')
        self.assertContains(respuesta, 'Consulta')
        self.assertNotContains(respuesta, 'Nuevo repuesto')
        self.assertNotContains(respuesta, 'Confirmar recepción')

    def test_recepcion_suma_existencia_y_consumo_la_descuenta(self):
        self.client.force_login(self.tecnico)
        datos_solicitud = {
            'repuestos-TOTAL_FORMS': '1',
            'repuestos-INITIAL_FORMS': '0',
            'repuestos-0-codigo': 'FILTRO-01',
            'repuestos-0-nombre': 'Filtro hidráulico',
            'repuestos-0-unidad_medida': 'pieza',
            'repuestos-0-cantidad': '3.00',
        }
        respuesta = self.client.post(
            reverse('ordenes_trabajo:solicitar_repuestos', args=[self.orden.pk]),
            datos_solicitud,
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        solicitud = SolicitudRepuesto.objects.get()

        self.client.force_login(self.administrador)
        respuesta = self.client.post(
            reverse(
                'ordenes_trabajo:resolver_solicitud_repuesto',
                args=[solicitud.pk, 'aprobar'],
            ),
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        respuesta = self.client.post(
            reverse(
                'ordenes_trabajo:resolver_solicitud_repuesto',
                args=[solicitud.pk, 'recibir'],
            ),
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        solicitud.refresh_from_db()
        repuesto = Repuesto.objects.get(codigo='FILTRO-01')
        self.assertEqual(solicitud.estado, 'recibida')
        self.assertEqual(repuesto.existencia, Decimal('3.00'))

        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:consumir_repuesto', args=[self.orden.pk]),
            {'repuesto': repuesto.pk, 'cantidad': '1.50'},
        )
        self.assertRedirects(
            respuesta,
            reverse('ordenes_trabajo:detalle', args=[self.orden.pk]),
        )
        repuesto.refresh_from_db()
        self.assertEqual(repuesto.existencia, Decimal('1.50'))
        self.assertEqual(ConsumoRepuesto.objects.get().cantidad, Decimal('1.50'))
