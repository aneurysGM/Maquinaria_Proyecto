from datetime import date, datetime, timedelta, timezone as tz
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.inventario.forms import MaquinariaIntegralForm
from apps.inventario.models import Unidad
from apps.ventas.models import PresupuestoAlquiler
from .models import SolicitudAlquiler
from .tests_datos import DatosIntegracion
from .views import sumar_seis_meses


class IntegracionAlquileresTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def test_flujo_completo_conserva_plan_presupuesto_horometro_e_historial(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.post(reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]), {
            'fecha_inicio': timezone.localdate().isoformat(), 'plan': 'semanal',
            'cantidad': 2, 'comentario': 'Obra integración',
        }, follow=True)
        self.assertEqual(respuesta.status_code, 200)
        solicitud = SolicitudAlquiler.objects.get()
        self.assertEqual(solicitud.fecha_fin, timezone.localdate() + timedelta(days=13))
        self.assertEqual(solicitud.presupuesto.importe_renta, Decimal('9000.00'))
        self.assertEqual(solicitud.presupuesto.importe_total, Decimal('12000.00'))
        self.assertContains(self.client.get(reverse('alquileres:solicitud_detalle', args=[solicitud.pk])), 'Obra integración')
        self.client.force_login(self.admin)
        self.client.post(reverse('alquileres:solicitud_resolver', args=[solicitud.pk]), {'decision': 'Aprobada'})
        self.client.post(reverse('alquileres:solicitud_salida', args=[solicitud.pk]))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.revisado_por, self.admin)
        self.assertEqual(solicitud.entregado_por, self.admin)
        self.assertIsNotNone(solicitud.fecha_salida)
        pendientes = self.client.get(reverse('alquileres:entrega_lista'))
        self.assertEqual(list(pendientes.context['entregas']), [solicitud])
        self.assertContains(pendientes, 'Historial completo')
        self.client.post(reverse('alquileres:solicitud_retorno', args=[solicitud.pk]), {
            'horas_uso_actualizadas': '17.5', 'observaciones_retorno': 'Sin daños',
        })
        solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(self.unidad.horas_uso, Decimal('17.5'))
        self.assertEqual(solicitud.recibido_por, self.admin)
        self.assertGreaterEqual(solicitud.fecha_retorno, solicitud.fecha_salida)
        self.assertEqual(solicitud.presupuesto.mora_total, 0)
        self.assertFalse(self.client.get(reverse('alquileres:entrega_lista')).context['entregas'])
        for estado in ('devueltas', 'todas'):
            self.assertEqual(list(self.client.get(reverse('alquileres:entrega_lista'), {'estado': estado}).context['entregas']), [solicitud])
        self.client.force_login(self.cliente)
        detalle = self.client.get(reverse('alquileres:solicitud_detalle', args=[solicitud.pk]))
        self.assertContains(detalle, 'Sin daños')
        self.assertContains(detalle, self.admin.email)
        self.assertNotContains(detalle, 'Registrar retorno')

    def test_tres_planes_y_tarifas_contratadas_no_cambian(self):
        self.client.force_login(self.cliente)
        for plan, dias, tarifa in [('diario', 2, 750), ('semanal', 14, 4500), ('mensual', 60, 15000)]:
            with self.subTest(plan=plan):
                self.client.post(reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]), {
                    'fecha_inicio': timezone.localdate().isoformat(), 'plan': plan, 'cantidad': 2,
                })
                solicitud = SolicitudAlquiler.objects.latest('pk')
                self.assertEqual((solicitud.fecha_fin - solicitud.fecha_inicio).days + 1, dias)
                self.assertEqual(solicitud.presupuesto.tarifa_periodo, tarifa)
                self.assertEqual(solicitud.presupuesto.importe_renta, tarifa * 2)
        self.maquinaria.tarifa_mensual = 16000
        self.maquinaria.save(update_fields=['tarifa_mensual'])
        self.assertEqual(PresupuestoAlquiler.objects.get(solicitud=solicitud).importe_renta, 30000)

    def test_duplicado_pendiente_no_crea_otro_presupuesto(self):
        self.client.force_login(self.cliente)
        datos = {'fecha_inicio': timezone.localdate().isoformat(), 'plan': 'diario', 'cantidad': 1}
        url = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk])
        self.client.post(url, datos)
        self.assertContains(self.client.post(url, datos), 'Ya tienes una solicitud pendiente')
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)
        self.assertEqual(PresupuestoAlquiler.objects.count(), 1)

    def test_solicitud_y_presupuesto_se_revierten_juntos(self):
        self.client.force_login(self.cliente)
        with patch('apps.alquileres.views.PresupuestoAlquiler.objects.create', side_effect=DatabaseError('fallo')):
            respuesta = self.client.post(reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]), {
                'fecha_inicio': timezone.localdate().isoformat(), 'plan': 'diario', 'cantidad': 1,
            })
        self.assertContains(respuesta, 'error de base de datos')
        self.assertFalse(SolicitudAlquiler.objects.exists())

    def test_duracion_invalida_no_crea_registros(self):
        self.client.force_login(self.cliente)
        for cantidad in ('0', '-1', '999999999999'):
            self.client.post(reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]), {
                'fecha_inicio': timezone.localdate().isoformat(), 'plan': 'mensual', 'cantidad': cantidad,
            })
        self.assertFalse(SolicitudAlquiler.objects.exists())

    def test_cliente_solo_ve_sus_solicitudes_y_detalles(self):
        propia = self.crear_solicitud(comentario='Comentario propio')
        ajena = self.crear_solicitud(cliente=self.otro, comentario='Comentario ajeno')
        self.client.force_login(self.cliente)
        respuesta = self.client.get(reverse('alquileres:solicitud_lista'), {'q': self.otro.email, 'cliente': self.otro.pk})
        self.assertEqual(list(respuesta.context['solicitudes']), [propia])
        self.assertNotContains(respuesta, 'Comentario ajeno')
        self.assertEqual(self.client.get(reverse('alquileres:solicitud_detalle', args=[ajena.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('alquileres:solicitud_detalle', args=[propia.pk])).status_code, 200)

    def test_superusuario_con_rol_cliente_ve_todas(self):
        self.crear_solicitud()
        self.crear_solicitud(cliente=self.otro)
        self.client.force_login(self.superadmin)
        self.assertEqual(len(self.client.get(reverse('alquileres:solicitud_lista')).context['solicitudes']), 2)

    def test_filtros_busqueda_estado_periodo_inclusivo_y_errores(self):
        hoy = timezone.localdate()
        elegida = self.crear_solicitud(estado='Aprobada', fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=7))
        self.crear_solicitud(cliente=self.otro, fecha_inicio=hoy + timedelta(days=20), fecha_fin=hoy + timedelta(days=21))
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_lista')
        for q in (self.cliente.email, 'Ana Pérez', '000123', 'Excavadora', '0000456', '#' + str(elegida.pk)):
            with self.subTest(q=q):
                respuesta = self.client.get(url, {'q': q, 'estado': 'Aprobada', 'desde': elegida.fecha_fin.isoformat(), 'hasta': elegida.fecha_fin.isoformat()})
                self.assertEqual(list(respuesta.context['solicitudes']), [elegida])
        for datos in ({'desde': 'incorrecta'}, {'estado': 'inventado'}, {'desde': '2026-11-10', 'hasta': '2026-11-09'}):
            respuesta = self.client.get(url, datos)
            self.assertTrue(respuesta.context['filtros'].errors)
            self.assertFalse(respuesta.context['solicitudes'])

    def test_aprobacion_rechaza_cruce_inclusivo_y_doble_revision(self):
        aprobada = self.crear_solicitud(estado='Aprobada', fecha_fin=timezone.localdate() + timedelta(days=5))
        pendiente = self.crear_solicitud(fecha_inicio=aprobada.fecha_fin, fecha_fin=aprobada.fecha_fin)
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_resolver', args=[pendiente.pk])
        self.client.post(url, {'decision': 'Aprobada'})
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, 'Pendiente')
        self.client.post(url, {'decision': 'Rechazada'})
        self.client.post(url, {'decision': 'Aprobada'})
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, 'Rechazada')

    def test_roles_csrf_get_y_campos_extra_no_autorizan_movimientos(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('alquileres:entrega_lista')).status_code, 403)
            for accion in ('solicitud_salida', 'solicitud_retorno', 'solicitud_resolver'):
                self.assertEqual(self.client.post(reverse('alquileres:' + accion, args=[solicitud.pk])).status_code, 403)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(reverse('alquileres:solicitud_salida', args=[solicitud.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.client.get(reverse('alquileres:solicitud_salida', args=[solicitud.pk]))
        solicitud.refresh_from_db()
        self.assertIsNone(solicitud.fecha_salida)
        self.client.post(reverse('alquileres:solicitud_salida', args=[solicitud.pk]), {'fecha_movimiento': '2000-01-01', 'entregado_por': self.otro.pk})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.entregado_por, self.admin)
        self.assertEqual(timezone.localtime(solicitud.fecha_salida).date(), timezone.localdate())

    def test_no_salida_antes_del_inicio_y_no_dos_salidas(self):
        futura = self.crear_solicitud(estado='Aprobada', fecha_inicio=timezone.localdate() + timedelta(days=1), fecha_fin=timezone.localdate() + timedelta(days=1))
        self.client.force_login(self.admin)
        self.client.post(reverse('alquileres:solicitud_salida', args=[futura.pk]))
        futura.refresh_from_db()
        self.assertIsNone(futura.fecha_salida)
        entrega = self.crear_entrega()
        self.client.post(reverse('alquileres:solicitud_salida', args=[entrega.pk]))
        entrega.refresh_from_db()
        self.assertEqual(entrega.fecha_salida.date(), (timezone.now() - timedelta(days=10)).date())

    def test_retorno_rechaza_horometro_menor_y_estado_inesperado(self):
        entrega = self.crear_entrega()
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_retorno', args=[entrega.pk])
        self.client.post(url, {'horas_uso_actualizadas': '9'})
        entrega.refresh_from_db()
        self.assertIsNone(entrega.fecha_retorno)
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Mantenimiento')
        self.client.post(url, {'horas_uso_actualizadas': '11'})
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Mantenimiento')

    def test_retorno_exento_no_cobra_ni_advierte_infraccion_ni_suspende(self):
        anterior = self.crear_entrega(atraso=5)
        anterior.fecha_retorno = timezone.now() - timedelta(days=1)
        anterior.recibido_por = self.admin
        anterior.dias_atraso = 4
        anterior.save()
        entrega = self.crear_entrega(atraso=5, politica_mora_aplica=False)
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '11'}, follow=True)
        entrega.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        self.assertIsNone(self.cliente.suspension_hasta)
        self.assertEqual(entrega.presupuesto.mora_total, 0)
        self.assertNotContains(respuesta, 'primera devolución con más de')
        self.assertContains(respuesta, 'Registro histórico exento')

    def test_segunda_infraccion_y_fecha_de_suspension_exacta(self):
        anterior = self.crear_entrega(atraso=5)
        anterior.fecha_retorno = timezone.now() - timedelta(days=1)
        anterior.recibido_por = self.admin
        anterior.dias_atraso = 4
        anterior.save()
        entrega = self.crear_entrega(atraso=4)
        self.client.force_login(self.admin)
        self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '11'})
        self.cliente.refresh_from_db()
        entrega.refresh_from_db()
        self.assertFalse(self.cliente.is_active)
        self.assertEqual(self.cliente.suspension_hasta, sumar_seis_meses(timezone.localdate()))
        self.assertEqual(entrega.presupuesto.mora_total, Decimal('375.00'))

    def test_fallo_de_horometro_revierte_retorno_mora_y_suspension(self):
        entrega = self.crear_entrega(atraso=4)
        self.client.force_login(self.admin)
        with patch('apps.inventario.models.Unidad.save', side_effect=DatabaseError('fallo')):
            respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '11'})
        self.assertEqual(respuesta.status_code, 302)
        entrega.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertIsNone(entrega.fecha_retorno)
        self.assertEqual(self.unidad.estado, 'Alquilado')
        self.assertEqual(self.unidad.horas_uso, Decimal('10.5'))
        self.assertEqual(entrega.presupuesto.mora_total, 0)

    def test_fallo_al_guardar_mora_revierte_solicitud_y_unidad(self):
        entrega = self.crear_entrega(atraso=4)
        self.client.force_login(self.admin)
        with patch('apps.ventas.models.PresupuestoAlquiler.save', side_effect=DatabaseError('fallo')):
            self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '18'})
        entrega.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertIsNone(entrega.fecha_retorno)
        self.assertEqual(self.unidad.estado, 'Alquilado')
        self.assertEqual(self.unidad.horas_uso, Decimal('10.5'))

    def test_infraccion_historica_exenta_no_cuenta_para_suspender(self):
        anterior = self.crear_entrega(atraso=5, politica_mora_aplica=False, presupuesto=False)
        anterior.fecha_retorno = timezone.now() - timedelta(days=1)
        anterior.recibido_por = self.admin
        anterior.dias_atraso = 4
        anterior.save()
        entrega = self.crear_entrega(atraso=4)
        self.client.force_login(self.admin)
        respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '11'}, follow=True)
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        self.assertContains(respuesta, 'primera devolución con más de 3 días')

    def test_retorno_de_unidad_inactiva_fecha_automatica_y_no_repeticion(self):
        entrega = self.crear_entrega(atraso=1)
        Unidad.objects.filter(pk=self.unidad.pk).update(activo=False)
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_retorno', args=[entrega.pk])
        self.client.post(url, {'horas_uso_actualizadas': '11', 'fecha_movimiento': '2000-01-01', 'recibido_por': self.otro.pk})
        entrega.refresh_from_db()
        fecha = entrega.fecha_retorno
        self.assertEqual(timezone.localtime(fecha).date(), timezone.localdate())
        self.assertEqual(entrega.recibido_por, self.admin)
        self.assertEqual(entrega.dias_atraso, 1)
        self.assertEqual(entrega.presupuesto.mora_total, 75)
        self.client.post(url, {'horas_uso_actualizadas': '50'})
        entrega.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(entrega.fecha_retorno, fecha)
        self.assertEqual(self.unidad.horas_uso, 11)
        self.assertFalse(self.unidad.activo)
        self.assertEqual(self.unidad.estado, 'Disponible')

    def test_proteccion_modelo_y_formulario_con_entrega_pendiente(self):
        self.crear_entrega()
        self.unidad.estado = 'Disponible'
        with self.assertRaises(ValidationError):
            self.unidad.clean()
        datos = dict(
            categoria=self.maquinaria.categoria_id, codigo=self.maquinaria.codigo,
            nombre=self.maquinaria.nombre, descripcion=self.maquinaria.descripcion,
            costo_adquisicion='90000', tarifa_diaria='750', tarifa_semanal='4500',
            tarifa_mensual='15000', deposito_garantia='3000', numero_serie=self.unidad.numero_serie,
            estado='Disponible', horas_uso='10.5', ubicacion_actual='Santo Domingo',
        )
        form = MaquinariaIntegralForm(datos, unidad=self.unidad)
        self.assertFalse(form.is_valid())
        self.assertIn('estado', form.errors)

    def test_guardado_revalida_entrega_que_aparecio_despues_del_formulario(self):
        datos = dict(
            categoria=self.maquinaria.categoria_id, codigo=self.maquinaria.codigo,
            nombre='Nombre que no debe guardarse', descripcion=self.maquinaria.descripcion,
            costo_adquisicion='90000', tarifa_diaria='750', tarifa_semanal='4500',
            tarifa_mensual='15000', deposito_garantia='3000', numero_serie=self.unidad.numero_serie,
            estado='Disponible', horas_uso='10.5', ubicacion_actual='Santo Domingo',
        )
        form = MaquinariaIntegralForm(datos, unidad=self.unidad)
        self.assertTrue(form.is_valid(), form.errors)
        self.crear_entrega()
        with self.assertRaises(ValidationError):
            form.save()
        self.unidad.refresh_from_db()
        self.maquinaria.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Alquilado')
        self.assertEqual(self.maquinaria.nombre, 'Excavadora integración')

    def test_avisos_vence_hoy_proximo_vencido_y_cambio_de_dia_local(self):
        entrega = self.crear_entrega()
        hoy = timezone.localdate()
        for diferencia, aviso in [(-1, 'Vencido'), (0, 'Vence hoy'), (1, 'Próximo a vencer'), (3, 'Próximo a vencer'), (4, '')]:
            entrega.fecha_fin = hoy + timedelta(days=diferencia)
            self.assertEqual(entrega.aviso_vencimiento, aviso)
        entrega.fecha_fin = date(2026, 11, 9)
        with patch('django.utils.timezone.now', return_value=datetime(2026, 11, 10, 2, tzinfo=tz.utc)):
            self.assertEqual(entrega.aviso_vencimiento, 'Vence hoy')
        entrega.fecha_retorno = timezone.now()
        self.assertEqual(entrega.aviso_vencimiento, '')


class SeisMesesTests(SimpleTestCase):
    def test_seis_meses_calendario_y_ultimo_dia(self):
        for inicio, fin in [(date(2026, 11, 9), date(2027, 5, 9)), (date(2026, 8, 31), date(2027, 2, 28)), (date(2027, 8, 31), date(2028, 2, 29))]:
            self.assertEqual(sumar_seis_meses(inicio), fin)
