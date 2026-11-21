from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.mantenimiento.models import Mantenimiento
from .models import (
    BorradorOrden, ComentarioOrden, ConsumoRepuesto, DetalleSolicitudRepuesto,
    EntradaRepuesto, PuntoChecklist, Repuesto, SolicitudRepuesto,
)


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
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('ordenes_trabajo:lista'))
        self.assertContains(respuesta, 'SERIE-OT-001')

    def datos_informe(self):
        return {
            'avance-estado': 'reparacion',
            'avance-dias_estimados': '3',
            'avance-horas_trabajo': '2.5',
            'avance-horometro': '120',
            'avance-observaciones': 'Se reparó la unidad.',
            'checklist-resultado_fluidos': 'correcto',
            'checklist-resultado_hidraulico': 'correcto',
            'checklist-resultado_rodaje': 'no_aplica',
            'checklist-resultado_electrico': 'correcto',
            'cierre-observaciones': 'Equipo probado y operativo.',
        }

    def test_borrador_parcial_se_recupera_sin_publicar_y_se_finaliza_en_un_envio(self):
        self.client.force_login(self.tecnico)
        url = reverse('ordenes_trabajo:informe', args=[self.orden.pk])
        datos = self.datos_informe()
        datos.update({
            'accion': 'borrador',
            'avance-dias_estimados': '',
            'checklist-resultado_electrico': '',
        })
        respuesta = self.client.post(url, datos)
        self.assertRedirects(respuesta, reverse('ordenes_trabajo:detalle', args=[self.orden.pk]))
        self.assertTrue(BorradorOrden.objects.filter(mantenimiento=self.orden).exists())
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'pendiente')
        self.assertEqual(self.unidad.horas_uso, Decimal('100.0'))
        self.assertEqual(self.orden.registros_trabajo.count(), 0)
        self.assertEqual(self.orden.puntos_checklist.count(), 0)
        respuesta = self.client.get(reverse('ordenes_trabajo:detalle', args=[self.orden.pk]))
        self.assertContains(respuesta, 'Hay un borrador guardado')
        self.assertContains(respuesta, 'Se reparó la unidad.')
        self.assertContains(respuesta, 'Equipo probado y operativo.')

        datos = self.datos_informe()
        datos['accion'] = 'finalizar'
        respuesta = self.client.post(url, datos)
        self.assertRedirects(respuesta, reverse('ordenes_trabajo:detalle', args=[self.orden.pk]))
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'finalizada')
        self.assertIsNotNone(self.orden.fecha_fin)
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(self.unidad.horas_uso, Decimal('120.0'))
        self.assertEqual(self.unidad.proximo_mantenimiento_horas, Decimal('170.0'))
        self.assertEqual(self.orden.horas_mano_obra_total, Decimal('2.5'))
        self.assertEqual(self.orden.puntos_checklist.count(), len(PuntoChecklist.PUNTOS))
        self.assertFalse(BorradorOrden.objects.filter(mantenimiento=self.orden).exists())
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('ordenes_trabajo:detalle', args=[self.orden.pk]))
        self.assertContains(respuesta, 'Niveles de fluidos')
        self.assertContains(respuesta, 'Equipo probado y operativo.')

    def test_informe_incompleto_o_repuestos_pendientes_no_publican_nada(self):
        self.client.force_login(self.tecnico)
        url = reverse('ordenes_trabajo:informe', args=[self.orden.pk])
        datos = self.datos_informe()
        datos.update({'accion': 'finalizar', 'checklist-resultado_electrico': ''})
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, 'Revisa los campos indicados')
        self.assertContains(respuesta, 'Se reparó la unidad.')
        self.assertEqual(self.orden.puntos_checklist.count(), 0)
        solicitud = SolicitudRepuesto.objects.create(
            mantenimiento=self.orden, solicitada_por=self.tecnico, estado='aprobada',
        )
        datos['checklist-resultado_electrico'] = 'correcto'
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, 'aprobadas sin recibir')
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'pendiente')
        self.assertEqual(self.unidad.horas_uso, Decimal('100.0'))
        self.assertEqual(self.orden.registros_trabajo.count(), 0)
        self.assertEqual(self.orden.puntos_checklist.count(), 0)

        solicitud.estado = 'recibida'
        solicitud.save(update_fields=['estado'])
        self.orden.estado = 'esperando_repuestos'
        self.orden.save(update_fields=['estado'])
        datos['avance-estado'] = 'esperando_repuestos'
        self.client.post(url, datos)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'finalizada')

    def test_informe_respeta_asignacion_y_otras_ordenes_abiertas(self):
        url = reverse('ordenes_trabajo:informe', args=[self.orden.pk])
        datos = self.datos_informe()
        datos['accion'] = 'finalizar'
        self.client.force_login(self.otro_tecnico)
        self.assertEqual(self.client.post(url, datos).status_code, 404)
        self.client.force_login(self.administrador)
        self.assertEqual(self.client.post(url, datos).status_code, 403)
        Mantenimiento.objects.create(
            unidad=self.unidad, fecha=date.today(), tipo='Preventivo',
            descripcion='Otra orden', costo=Decimal('0'), tecnico=self.tecnico,
        )
        self.client.force_login(self.tecnico)
        self.client.post(url, datos)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Mantenimiento')

    def test_estado_finalizada_en_borrador_y_cierre_controlado(self):
        self.client.force_login(self.tecnico)
        detalle = reverse('ordenes_trabajo:detalle', args=[self.orden.pk])
        url = reverse('ordenes_trabajo:informe', args=[self.orden.pk])
        self.assertContains(self.client.get(detalle), '<option value="finalizada">Finalizada</option>', html=True)
        datos = self.datos_informe()
        datos.update({'accion': 'borrador', 'avance-estado': 'finalizada'})
        self.client.post(url, datos)
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'pendiente')
        self.assertIsNone(self.orden.fecha_fin)
        self.assertEqual(self.unidad.estado, 'Mantenimiento')
        self.assertContains(self.client.get(detalle), '<option value="finalizada" selected>Finalizada</option>', html=True)

        solicitud = SolicitudRepuesto.objects.create(
            mantenimiento=self.orden, solicitada_por=self.tecnico, estado='pendiente',
        )
        datos['accion'] = 'finalizar'
        respuesta = self.client.post(url, datos)
        self.assertContains(respuesta, 'solicitudes de repuestos pendientes')
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'pendiente')
        self.assertEqual(self.orden.registros_trabajo.count(), 0)
        self.assertTrue(BorradorOrden.objects.filter(mantenimiento=self.orden).exists())
        solicitud.estado = 'recibida'
        solicitud.save(update_fields=['estado'])
        self.client.post(url, datos)
        self.orden.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.orden.estado, 'finalizada')
        self.assertIsNotNone(self.orden.fecha_fin)
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(self.orden.horas_mano_obra_total, Decimal('2.5'))

    def test_finalizacion_exige_checklist_y_programa_proximo_servicio(self):
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:actualizar', args=[self.orden.pk]),
            {
                'estado': 'reparacion',
                'dias_estimados': '3',
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

    def test_estimacion_en_diagnostico_y_reparacion(self):
        self.client.force_login(self.tecnico)
        url = reverse('ordenes_trabajo:actualizar', args=[self.orden.pk])
        datos = {'estado': 'diagnostico', 'horas_trabajo': '0',
                 'horometro': '100', 'observaciones': 'Revisión'}
        self.client.post(url, datos)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'diagnostico')
        self.assertIsNone(self.orden.fecha_estimada_fin)

        datos['estado'] = 'reparacion'
        respuesta = self.client.post(url, datos, follow=True)
        self.assertContains(respuesta, 'Indica los días estimados')
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'diagnostico')

        datos['dias_estimados'] = '4'
        self.client.post(url, datos)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.fecha_estimada_fin, timezone.localdate() + timedelta(days=4))
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('ordenes_trabajo:detalle', args=[self.orden.pk]))
        self.assertContains(respuesta, self.orden.fecha_estimada_fin.strftime('%d/%m/%Y'))

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

    def test_tecnico_recibe_solicitud_aprobada_y_finaliza_orden(self):
        self.client.force_login(self.tecnico)
        self.client.post(
            reverse('ordenes_trabajo:solicitar_repuestos', args=[self.orden.pk]),
            {
                'repuestos-TOTAL_FORMS': '1',
                'repuestos-INITIAL_FORMS': '0',
                'repuestos-0-codigo': 'NUEVO-01',
                'repuestos-0-nombre': 'Pieza nueva',
                'repuestos-0-unidad_medida': 'pieza',
                'repuestos-0-cantidad': '2.00',
            },
        )
        solicitud = SolicitudRepuesto.objects.get()
        recibir = reverse(
            'ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'recibir'],
        )
        self.client.post(recibir)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'pendiente')
        self.assertFalse(Repuesto.objects.filter(codigo='NUEVO-01').exists())

        self.client.force_login(self.administrador)
        self.client.post(reverse(
            'ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'aprobar'],
        ))
        self.client.force_login(self.tecnico)
        detalle = reverse('ordenes_trabajo:detalle', args=[self.orden.pk])
        self.assertContains(self.client.get(detalle), recibir)
        self.assertContains(self.client.get(reverse('Repuestos_Inventario:lista')), recibir)

        datos = {**self.datos_informe(), 'accion': 'finalizar'}
        self.assertContains(
            self.client.post(reverse('ordenes_trabajo:informe', args=[self.orden.pk]), datos),
            'aprobadas sin recibir',
        )
        self.client.post(recibir)
        solicitud.refresh_from_db()
        repuesto = Repuesto.objects.get(codigo='NUEVO-01')
        self.assertEqual(solicitud.estado, 'recibida')
        self.assertEqual(repuesto.existencia, Decimal('2.00'))
        self.assertEqual(EntradaRepuesto.objects.get(solicitud=solicitud).registrado_por, self.tecnico)
        self.assertEqual(solicitud.detalles.get().repuesto, repuesto)

        self.client.post(recibir)
        repuesto.refresh_from_db()
        self.assertEqual(repuesto.existencia, Decimal('2.00'))
        self.assertEqual(EntradaRepuesto.objects.filter(solicitud=solicitud).count(), 1)

        self.client.post(reverse('ordenes_trabajo:informe', args=[self.orden.pk]), datos)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, 'finalizada')

    def test_solo_tecnico_asignado_puede_recibir_y_no_puede_aprobar(self):
        solicitud = SolicitudRepuesto.objects.create(
            mantenimiento=self.orden, solicitada_por=self.tecnico, estado='pendiente',
        )
        DetalleSolicitudRepuesto.objects.create(
            solicitud=solicitud, codigo='SEG-01', nombre='Pieza',
            unidad_medida='pieza', cantidad=Decimal('1.00'),
        )
        aprobar = reverse(
            'ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'aprobar'],
        )
        recibir = reverse(
            'ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'recibir'],
        )
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.post(aprobar).status_code, 403)
        solicitud.estado = 'aprobada'
        solicitud.save(update_fields=['estado'])
        self.client.force_login(self.otro_tecnico)
        self.assertEqual(self.client.post(recibir).status_code, 404)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'aprobada')
        self.assertFalse(EntradaRepuesto.objects.exists())

    def test_error_de_unidad_revierte_recepcion_completa(self):
        solicitud = SolicitudRepuesto.objects.create(
            mantenimiento=self.orden, solicitada_por=self.tecnico, estado='aprobada',
        )
        DetalleSolicitudRepuesto.objects.create(
            solicitud=solicitud, codigo='NUEVO-ROLLBACK', nombre='Pieza nueva',
            unidad_medida='pieza', cantidad=Decimal('2.00'),
        )
        repuesto = Repuesto.objects.create(
            codigo='EXISTENTE', nombre='Aceite', unidad_medida='litro',
            existencia=Decimal('5.00'),
        )
        DetalleSolicitudRepuesto.objects.create(
            solicitud=solicitud, codigo='EXISTENTE', nombre='Aceite',
            unidad_medida='pieza', cantidad=Decimal('1.00'),
        )
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'recibir']),
            follow=True,
        )
        self.assertContains(respuesta, 'no coincide con el catálogo')
        solicitud.refresh_from_db()
        repuesto.refresh_from_db()
        self.assertEqual(solicitud.estado, 'aprobada')
        self.assertEqual(repuesto.existencia, Decimal('5.00'))
        self.assertFalse(Repuesto.objects.filter(codigo='NUEVO-ROLLBACK').exists())
        self.assertFalse(EntradaRepuesto.objects.filter(solicitud=solicitud).exists())
        self.assertFalse(solicitud.detalles.filter(repuesto__isnull=False).exists())

    def test_tecnico_no_puede_recibir_en_orden_finalizada(self):
        solicitud = SolicitudRepuesto.objects.create(
            mantenimiento=self.orden, solicitada_por=self.tecnico, estado='aprobada',
        )
        DetalleSolicitudRepuesto.objects.create(
            solicitud=solicitud, codigo='FIN-01', nombre='Pieza',
            unidad_medida='pieza', cantidad=Decimal('1.00'),
        )
        self.orden.estado = 'finalizada'
        self.orden.fecha_fin = timezone.localdate()
        self.orden.save(update_fields=['estado', 'fecha_fin'])
        self.client.force_login(self.tecnico)
        respuesta = self.client.post(
            reverse('ordenes_trabajo:resolver_solicitud_repuesto', args=[solicitud.pk, 'recibir']),
            follow=True,
        )
        self.assertContains(respuesta, 'orden finalizada')
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'aprobada')
        self.assertFalse(EntradaRepuesto.objects.filter(solicitud=solicitud).exists())
