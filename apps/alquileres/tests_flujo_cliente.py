"""Aceptación del flujo Cliente y confirmación administrativa por pago."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core import signing
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import UsuarioPersonalizado, RolUsuario
from apps.inventario.models import Unidad
from apps.ventas.models import PagoAlquiler, ReembolsoDeposito
from apps.ventas.views import datos_revision
from .models import SolicitudAlquiler
from .reservas import solicitudes_afectadas
from .tests_datos import DatosIntegracion


class FlujoClienteTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def aprobar(self, solicitud):
        self.client.force_login(self.admin)
        return self.client.post(reverse('alquileres:solicitud_resolver', args=[solicitud.pk]), {'decision': 'Aprobada'})

    def pago(self, solicitud, concepto, monto, **extras):
        self.client.force_login(self.admin)
        return self.client.post(reverse('ventas:pago_registrar', args=[solicitud.presupuesto.pk]),
                                {'concepto': concepto, 'monto': monto, 'metodo': 'efectivo', **extras})

    def revision(self, solicitud):
        return signing.dumps(datos_revision(solicitud, list(solicitudes_afectadas(solicitud))), salt='confirmar-reserva')

    def pagar_renta(self, solicitud):
        return self.pago(solicitud, 'renta', str(solicitud.presupuesto.importe_renta))

    def confirmar(self, solicitud, **motivos):
        return self.pago(solicitud, 'deposito', str(solicitud.presupuesto.deposito_garantia),
                         revision_reserva=self.revision(solicitud), **motivos)

    def test_ana_luis_carla_aprobacion_pago_rechazo_y_presupuesto(self):
        inicio = timezone.localdate() + timedelta(days=5)
        ana = self.crear_solicitud(fecha_inicio=inicio, fecha_fin=inicio + timedelta(days=2))
        luis = self.crear_solicitud(cliente=self.otro, plan='semanal', comentario='Comentario original de Luis',
                                   fecha_inicio=inicio + timedelta(days=1), fecha_fin=inicio + timedelta(days=7))
        carla_usuario = UsuarioPersonalizado.objects.create_user(email='carla@example.com', rol=RolUsuario.CLIENTE)
        carla = self.crear_solicitud(cliente=carla_usuario, fecha_inicio=inicio + timedelta(days=8), fecha_fin=inicio + timedelta(days=14))
        self.aprobar(ana)
        for s, esperado in [(ana, 'Pendiente de pago'), (luis, 'Pendiente de aprobación'), (carla, 'Pendiente de aprobación')]:
            s.refresh_from_db()
            self.assertEqual(s.estado_cliente, esperado)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.pagar_renta(ana)
        motivo = f'La excavadora quedó reservada del {inicio:%d/%m/%Y} al {ana.fecha_fin:%d/%m/%Y}.'
        respuesta = self.confirmar(ana, **{f'motivo_{luis.pk}': motivo})
        self.assertEqual(respuesta.status_code, 302)
        ana.refresh_from_db()
        luis.refresh_from_db()
        carla.refresh_from_db()
        self.assertIsNotNone(ana.fecha_confirmacion)
        self.assertEqual(ana.estado_cliente, 'Pendiente de entrega')
        self.assertEqual(luis.estado_cliente, 'Rechazado')
        self.assertEqual(luis.motivo_rechazo, motivo)
        self.assertEqual(luis.comentario, 'Comentario original de Luis')
        self.assertEqual(carla.estado_cliente, 'Pendiente de aprobación')
        self.client.force_login(self.otro)
        self.assertContains(self.client.get(reverse('alquileres:solicitud_lista')), 'Ver motivo')
        detalle = self.client.get(reverse('alquileres:solicitud_detalle', args=[luis.pk]))
        self.assertContains(detalle, motivo)
        self.assertContains(detalle, 'Tu solicitud de alquiler fue rechazada')
        catalogo = reverse('inventario:maquinaria_lista') + f'?categoria={self.maquinaria.categoria_id}'
        fechas = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]) + '?plan=semanal&cantidad=1'
        self.assertContains(detalle, catalogo)
        self.assertContains(detalle, fechas.replace('&', '&amp;'))
        self.assertContains(self.client.get(catalogo), 'Limpiar filtros')
        formulario = self.client.get(fechas)
        self.assertEqual(formulario.context['form'].initial['plan'], 'semanal')
        self.assertEqual(formulario.context['periodos_ocupados'], [{'inicio': ana.fecha_inicio.isoformat(), 'fin': ana.fecha_fin.isoformat()}])
        self.assertContains(formulario, 'Disponibles para solicitar')
        self.assertContains(formulario, 'Ocupadas')
        self.aprobar(carla)
        carla.refresh_from_db()
        self.assertEqual(carla.estado_cliente, 'Pendiente de pago')
        self.client.force_login(carla_usuario)
        self.assertContains(self.client.get(reverse('alquileres:solicitud_lista')), reverse('ventas:presupuesto_detalle', args=[carla.presupuesto.pk]))

    def test_calendario_valida_todo_el_plan_y_reintento_conserva_historial(self):
        inicio = timezone.localdate() + timedelta(days=5)
        reserva = self.crear_solicitud(estado='Aprobada', fecha_inicio=inicio, fecha_fin=inicio)
        self.pagar_renta(reserva)
        self.confirmar(reserva)
        rechazada = self.crear_solicitud(cliente=self.otro, estado='Rechazada', motivo_rechazo='Reservada', plan='semanal')
        self.client.force_login(self.otro)
        url = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk])
        for fecha, plan, cantidad in [(inicio - timedelta(days=1), 'semanal', 1), (inicio, 'diario', 1), (inicio - timedelta(days=2), 'diario', 3), (inicio - timedelta(days=3), 'mensual', 1)]:
            respuesta = self.client.post(url, {'fecha_inicio': fecha.isoformat(), 'plan': plan, 'cantidad': cantidad})
            self.assertContains(respuesta, 'Elige otras fechas')
            self.assertTrue(respuesta.context['form'].is_bound)
        self.assertEqual(SolicitudAlquiler.objects.count(), 2)
        respuesta = self.client.post(url, {'fecha_inicio': (inicio + timedelta(days=1)).isoformat(), 'plan': 'semanal', 'cantidad': 1})
        self.assertEqual(respuesta.status_code, 302)
        nueva = SolicitudAlquiler.objects.latest('pk')
        self.assertEqual(nueva.estado_cliente, 'Pendiente de aprobación')
        rechazada.refresh_from_db()
        self.assertEqual(rechazada.estado, 'Rechazada')

    def test_nueva_reserva_tras_abrir_formulario_se_revalida_al_enviar(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        self.client.force_login(self.otro)
        url = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk])
        self.assertEqual(self.client.get(url).context['periodos_ocupados'], [])
        self.pagar_renta(solicitud)
        self.confirmar(solicitud)
        self.client.force_login(self.otro)
        respuesta = self.client.post(url, {'fecha_inicio': solicitud.fecha_inicio.isoformat(), 'plan': 'diario', 'cantidad': 1})
        self.assertContains(respuesta, 'La disponibilidad cambió')
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)

    def test_motivo_obligatorio_y_revision_cambiada_no_guardan_pago(self):
        ana = self.crear_solicitud(estado='Aprobada')
        luis = self.crear_solicitud(cliente=self.otro)
        self.pagar_renta(ana)
        self.assertContains(self.confirmar(ana), 'Escribe un motivo para cada solicitud')
        revision = self.revision(ana)
        otra = self.crear_solicitud()
        respuesta = self.pago(ana, 'deposito', '3000', revision_reserva=revision, **{f'motivo_{luis.pk}': 'Reservada'})
        self.assertContains(respuesta, 'Cambió la lista')
        self.assertContains(respuesta, f'Solicitud #{otra.pk}')
        self.assertContains(respuesta, 'Reservada')
        self.assertEqual(PagoAlquiler.objects.count(), 1)
        ana.refresh_from_db()
        self.assertIsNone(ana.fecha_confirmacion)
        self.assertEqual(SolicitudAlquiler.objects.filter(estado='Rechazada').count(), 0)

    def test_revision_detecta_fechas_y_firma_alteradas(self):
        ana = self.crear_solicitud(estado='Aprobada')
        luis = self.crear_solicitud()
        self.pagar_renta(ana)
        revision = self.revision(ana)
        luis.fecha_fin += timedelta(days=1)
        luis.save()
        for firma in [revision, 'alterada']:
            respuesta = self.pago(ana, 'deposito', '3000', revision_reserva=firma, **{f'motivo_{luis.pk}': 'Reservada'})
            self.assertContains(respuesta, 'Revisa el formulario')
        self.assertEqual(PagoAlquiler.objects.count(), 1)

    def test_fallo_de_rechazo_revierte_pago_confirmacion_y_todos_los_rechazos(self):
        ana = self.crear_solicitud(estado='Aprobada')
        luis = self.crear_solicitud()
        otra = self.crear_solicitud()
        self.pagar_renta(ana)
        guardar = SolicitudAlquiler.save
        def fallar(solicitud, *args, **kwargs):
            if solicitud.pk == otra.pk:
                raise DatabaseError('Fallo de rechazo')
            return guardar(solicitud, *args, **kwargs)
        with patch.object(SolicitudAlquiler, 'save', fallar):
            respuesta = self.confirmar(ana, **{f'motivo_{luis.pk}': 'Reservada', f'motivo_{otra.pk}': 'Reservada'})
        self.assertContains(self.client.get(respuesta.url), 'No se guardaron cambios')
        ana.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertIsNone(ana.fecha_confirmacion)
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(PagoAlquiler.objects.count(), 1)
        self.assertFalse(SolicitudAlquiler.objects.filter(estado='Rechazada').exists())

    def test_confirmacion_revalida_unidad_y_reserva_confirmada(self):
        ana = self.crear_solicitud(estado='Aprobada')
        self.pagar_renta(ana)
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Mantenimiento')
        self.assertContains(self.confirmar(ana), 'ya no está disponible')
        self.assertEqual(PagoAlquiler.objects.count(), 1)

    def test_pago_parcial_no_rechaza_y_renta_sola_no_confirma(self):
        ana = self.crear_solicitud(estado='Aprobada')
        luis = self.crear_solicitud()
        self.pagar_renta(ana)
        self.pago(ana, 'deposito', '2999.99')
        ana.refresh_from_db()
        luis.refresh_from_db()
        self.assertEqual(ana.estado_cliente, 'Pendiente de pago')
        self.assertEqual(luis.estado_cliente, 'Pendiente de aprobación')
        self.assertIsNone(ana.fecha_confirmacion)
        self.assertContains(self.confirmar(ana), 'supera el saldo')

    def test_pago_final_de_renta_con_deposito_completo_confirma(self):
        ana = self.crear_solicitud(estado='Aprobada')
        self.pago(ana, 'deposito', '3000')
        self.pago(ana, 'renta', '750', revision_reserva=self.revision(ana))
        ana.refresh_from_db()
        self.assertEqual(ana.estado_cliente, 'Pendiente de entrega')
        self.assertIsNotNone(ana.fecha_confirmacion)

    def test_rechazos_solo_afectan_misma_unidad_y_cruces_inclusivos_vigentes(self):
        inicio = timezone.localdate() + timedelta(days=5)
        ana = self.crear_solicitud(estado='Aprobada', fecha_inicio=inicio, fecha_fin=inicio + timedelta(days=2))
        borde = self.crear_solicitud(fecha_inicio=ana.fecha_fin, fecha_fin=ana.fecha_fin + timedelta(days=1))
        aprobada = self.crear_solicitud(estado='Aprobada', fecha_inicio=inicio, fecha_fin=inicio)
        libre = self.crear_solicitud(fecha_inicio=ana.fecha_fin + timedelta(days=1), fecha_fin=ana.fecha_fin + timedelta(days=1))
        expirada = self.crear_solicitud(estado='Aprobada', fecha_revision=timezone.now() - timedelta(days=6), fecha_inicio=inicio, fecha_fin=inicio)
        otra_unidad = Unidad.objects.create(maquinaria=self.maquinaria, numero_serie='OTRA-UNIDAD', ubicacion_actual='Santo Domingo')
        otra = self.crear_solicitud(unidad=otra_unidad, fecha_inicio=inicio, fecha_fin=ana.fecha_fin)
        self.pagar_renta(ana)
        self.assertEqual([s.pk for s in solicitudes_afectadas(ana)], [borde.pk, aprobada.pk])
        self.confirmar(ana, **{f'motivo_{borde.pk}': 'Cruce inclusive', f'motivo_{aprobada.pk}': 'Reserva confirmada'})
        for s in (borde, aprobada):
            s.refresh_from_db()
            self.assertEqual(s.estado, 'Rechazada')
        for s in (libre, otra):
            s.refresh_from_db()
            self.assertEqual(s.estado_cliente, 'Pendiente de aprobación')
        expirada.refresh_from_db()
        self.assertEqual(expirada.estado_cliente, 'Vencido')

    def test_sin_cruces_tambien_exige_revision_y_no_repite_pago_final(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        self.pagar_renta(solicitud)
        self.assertContains(self.pago(solicitud, 'deposito', '3000'), 'falta su revisión')
        respuesta = self.confirmar(solicitud)
        self.assertEqual(respuesta.status_code, 302)
        self.pago(solicitud, 'deposito', '3000', revision_reserva=self.revision(solicitud))
        self.assertEqual(PagoAlquiler.objects.count(), 2)

    def test_pago_fuera_de_plazo_e_importes_manipulados_no_confirman(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        for monto in ['-1', '0', '750.01']:
            self.pago(solicitud, 'renta', monto)
        self.assertEqual(PagoAlquiler.objects.count(), 0)
        solicitud.fecha_revision = timezone.now() - timedelta(days=6)
        solicitud.save()
        self.pagar_renta(solicitud)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'Vencida')
        self.assertIsNone(solicitud.fecha_confirmacion)
        self.assertEqual(PagoAlquiler.objects.count(), 0)

    def test_rechazo_manual_exige_motivo_y_conserva_comentario(self):
        solicitud = self.crear_solicitud(comentario='Obra original')
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_resolver', args=[solicitud.pk])
        self.client.post(url, {'decision': 'Rechazada', 'motivo_rechazo': '  '})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'Pendiente')
        self.client.post(url, {'decision': 'Rechazada', 'motivo_rechazo': '  Motivo real  '})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.motivo_rechazo, 'Motivo real')
        self.assertEqual(solicitud.comentario, 'Obra original')

    def test_inicio_y_urls_directas_solo_permiten_datos_propios(self):
        propia = self.crear_solicitud(comentario='SOLO ANA')
        ajena = self.crear_solicitud(cliente=self.otro, comentario='SOLO LUIS')
        self.client.force_login(self.cliente)
        inicio = self.client.get(reverse('cuentas:dashboard'))
        self.assertContains(inicio, 'SOLO ANA')
        self.assertNotContains(inicio, 'SOLO LUIS')
        for nombre, pk in [('alquileres:solicitud_detalle', ajena.pk), ('ventas:presupuesto_detalle', ajena.presupuesto.pk)]:
            self.assertEqual(self.client.get(reverse(nombre, args=[pk])).status_code, 404)
        for nombre in ['ventas:pago_registrar', 'ventas:reembolso_registrar']:
            self.assertEqual(self.client.post(reverse(nombre, args=[ajena.presupuesto.pk]), {'monto': 1}).status_code, 403)
        self.assertContains(self.client.get(reverse('alquileres:solicitud_lista')), f'Solicitud #{propia.pk}')

    def test_vencido_y_devuelto_solo_aparecen_en_historial_y_en_uso_indica_fecha(self):
        vencida = self.crear_solicitud(estado='Aprobada', fecha_revision=timezone.now() - timedelta(days=6))
        devuelta = self.crear_entrega(fecha_retorno=timezone.now(), recibido_por=self.admin)
        en_uso = self.crear_entrega()
        self.client.force_login(self.cliente)
        self.assertEqual(vencida.estado_cliente, 'Vencido')
        self.assertEqual(devuelta.estado_cliente, 'Devuelto')
        self.assertEqual(en_uso.estado_cliente, 'En uso')
        inicio = self.client.get(reverse('cuentas:dashboard'))
        self.assertEqual([s.pk for s in inicio.context['solicitudes']], [en_uso.pk])
        self.assertContains(inicio, 'Fecha prevista de devolución')
        historial = self.client.get(reverse('alquileres:solicitud_lista'))
        self.assertContains(historial, 'Volver a solicitar')
        self.assertContains(historial, 'Devuelto')

    def test_entrega_exige_pago_y_luego_avanza_hasta_devuelto(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        self.client.force_login(self.admin)
        salida = reverse('alquileres:solicitud_salida', args=[solicitud.pk])
        self.client.post(salida)
        solicitud.refresh_from_db()
        self.assertIsNone(solicitud.fecha_salida)
        self.pagar_renta(solicitud)
        self.confirmar(solicitud)
        self.client.post(salida)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado_cliente, 'En uso')
        self.client.post(reverse('alquileres:solicitud_retorno', args=[solicitud.pk]), {'horas_uso_actualizadas': '11'})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado_cliente, 'Devuelto')

    def test_reembolso_del_deposito_no_reduce_renta_pendiente(self):
        solicitud = self.crear_entrega(fecha_retorno=timezone.now(), recibido_por=self.admin)
        presupuesto = solicitud.presupuesto
        PagoAlquiler.objects.create(presupuesto=presupuesto, concepto='deposito', monto=3000, metodo='efectivo', registrado_por=self.admin)
        PagoAlquiler.objects.create(presupuesto=presupuesto, concepto='renta', monto=250, metodo='efectivo', registrado_por=self.admin)
        for monto in (1000, 2000):
            ReembolsoDeposito.objects.create(presupuesto=presupuesto, monto=monto, metodo='efectivo', registrado_por=self.admin)
            self.assertEqual(presupuesto.renta_pendiente, Decimal('500.00'))
            self.assertEqual(presupuesto.saldo_pendiente, Decimal('500.00'))
            self.assertEqual(presupuesto.saldo_pendiente_actual, Decimal('500.00'))
