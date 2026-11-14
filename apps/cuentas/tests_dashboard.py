"""Indicadores y bandejas del Administrador con datos temporales."""
from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alquileres.tests_datos import DatosIntegracion
from apps.inventario.models import Unidad
from apps.mantenimiento.models import Mantenimiento
from apps.ventas.models import PagoAlquiler


@override_settings(TIME_ZONE='America/Santo_Domingo')
class DashboardAdministradorTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def setUp(self):
        self.client.force_login(self.admin)

    def panel(self):
        return self.client.get(reverse('cuentas:dashboard'))

    def unidad_adicional(self, estado='Disponible'):
        return Unidad.objects.create(maquinaria=self.maquinaria,
                                     numero_serie=f'PANEL-{Unidad.objects.count()}',
                                     ubicacion_actual='Taller de pruebas', estado=estado)

    def mantenimiento(self, **campos):
        datos = dict(unidad=self.unidad, fecha=timezone.localdate(), tipo='Preventivo',
                     descripcion='Trabajo temporal', costo=0, tecnico=self.tecnico)
        datos.update(campos)
        return Mantenimiento.objects.create(**datos)

    def pago(self, presupuesto, concepto, monto, fecha=None):
        datos = dict(presupuesto=presupuesto, concepto=concepto, monto=Decimal(monto),
                     metodo='efectivo', registrado_por=self.admin)
        if fecha is not None:
            datos['creado_en'] = fecha
        return PagoAlquiler.objects.create(**datos)

    def test_ceros_y_listas_vacias(self):
        Unidad.objects.update(estado='Baja')
        respuesta = self.panel()
        self.assertEqual(respuesta.context['kpis'], {
            'disponibles': 0, 'solicitudes_pendientes': 0, 'alquileres_activos': 0,
            'en_mantenimiento': 0, 'ingresos_mes': Decimal('0.00'),
        })
        self.assertContains(respuesta, 'RD$0.00')
        for nombre in ('Solicitudes por revisar', 'Alquileres activos', 'En mantenimiento'):
            self.assertContains(respuesta, f'<div class="kpi-num">0</div><div class="small text-secondary">{nombre}</div>', html=True)
        for mensaje in ('No hay solicitudes pendientes.', 'No hay mantenimientos por atender.', 'No hay pagos vencidos.'):
            self.assertContains(respuesta, mensaje)
        self.assertNotContains(respuesta, 'Facturas vencidas')

    def test_activos_incluye_legacy_reserva_y_pagados_sin_duplicar(self):
        antigua = self.crear_entrega(presupuesto=False, politica_mora_aplica=False)
        confirmada = self.crear_solicitud(estado='Aprobada', fecha_confirmacion=timezone.now(),
                                         unidad=self.unidad_adicional(), fecha_revision=timezone.now())
        # Varios pagos y entrega no duplican una solicitud confirmada.
        entregada = self.crear_entrega(unidad=self.unidad_adicional())
        for s in (confirmada, entregada):
            self.pago(s.presupuesto, 'renta', '250')
            self.pago(s.presupuesto, 'renta', '500')
            self.pago(s.presupuesto, 'deposito', '3000')
        self.crear_solicitud(estado='Aprobada', unidad=self.unidad_adicional())
        self.crear_solicitud(estado='Vencida', unidad=self.unidad_adicional())
        self.crear_entrega(unidad=self.unidad_adicional(), fecha_retorno=timezone.now(), recibido_por=self.admin)
        self.assertIsNone(antigua.fecha_confirmacion)
        self.assertEqual(self.panel().context['kpis']['alquileres_activos'], 3)

    def test_disponibles_conserva_criterio_del_inventario_del_admin(self):
        propia = self.unidad_adicional()
        self.maquinaria.registrada_por = self.admin
        self.maquinaria.save()
        self.unidad_adicional('Mantenimiento')
        self.unidad_adicional('Alquilado')
        respuesta = self.panel()
        self.assertEqual(respuesta.context['kpis']['disponibles'], 2)
        self.assertIn(propia, respuesta.context['maquinarias_disponibles'])

    def test_mantenimiento_cuenta_unidades_y_muestra_trabajos_abiertos_y_futuros(self):
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Mantenimiento')
        abierto = self.mantenimiento(fecha=timezone.localdate() - timedelta(days=1), tipo='Correctivo')
        futuro = self.mantenimiento(fecha=timezone.localdate() + timedelta(days=7))
        cerrado = self.mantenimiento(fecha_fin=timezone.localdate())
        respuesta = self.panel()
        self.assertEqual(respuesta.context['kpis']['en_mantenimiento'], 1)
        self.assertEqual(respuesta.context['mantenimientos_atencion_total'], 2)
        self.assertEqual(list(respuesta.context['mantenimientos_atencion']), [abierto, futuro])
        self.assertNotIn(cerrado, respuesta.context['mantenimientos_atencion'])
        self.assertContains(respuesta, 'Correctivo')
        self.assertContains(respuesta, 'Programado:')
        for m in (abierto, futuro):
            url = reverse('mantenimiento:mantenimiento_historial', args=[m.unidad_id])
            self.assertContains(respuesta, f'{url}#mantenimiento-{m.pk}')
            self.assertContains(self.client.get(url), f'id="mantenimiento-{m.pk}"')

    def test_ingresos_mes_respeta_limites_locales_excluye_deposito_y_otros_meses(self):
        ahora = datetime(2026, 11, 13, 18, tzinfo=utc.utc)
        inicio = datetime(2026, 11, 1, 4, tzinfo=utc.utc)
        fin = datetime(2026, 12, 1, 4, tzinfo=utc.utc)
        s = self.crear_solicitud(estado='Aprobada', politica_mora_aplica=False)
        p = s.presupuesto
        p.mora_total = Decimal('500')
        p.save()
        for concepto, monto, fecha in [
            ('renta', '11', inicio - timedelta(microseconds=1)),
            ('renta', '12', inicio),
            ('mora', '13', fin - timedelta(microseconds=1)),
            ('mora', '14', fin),
            ('renta', '50', ahora),
            ('deposito', '3000', ahora),
        ]:
            self.pago(p, concepto, monto, fecha)
        # La zona activa no debe desplazar el mes de la zona configurada del proyecto.
        with timezone.override('UTC'), patch('apps.cuentas.views.timezone.now', return_value=ahora):
            respuesta = self.panel()
        self.assertEqual(respuesta.context['kpis']['ingresos_mes'], Decimal('75.00'))
        self.assertContains(respuesta, 'RD$75.00')

    def test_ingresos_cambio_de_anio_y_solo_deposito_da_cero(self):
        ahora = datetime(2027, 1, 15, 12, tzinfo=utc.utc)
        s = self.crear_solicitud(estado='Aprobada')
        self.pago(s.presupuesto, 'deposito', '3000', ahora)
        with patch('apps.cuentas.views.timezone.now', return_value=ahora):
            self.client.force_login(self.admin)
            self.assertEqual(self.panel().context['kpis']['ingresos_mes'], Decimal('0'))
        self.pago(s.presupuesto, 'renta', '10', datetime(2027, 1, 1, 3, 59, 59, tzinfo=utc.utc))
        self.pago(s.presupuesto, 'renta', '20', datetime(2027, 1, 1, 4, tzinfo=utc.utc))
        self.pago(s.presupuesto, 'renta', '30', datetime(2027, 2, 1, 4, tzinfo=utc.utc))
        with patch('apps.cuentas.views.timezone.now', return_value=ahora):
            self.assertEqual(self.panel().context['kpis']['ingresos_mes'], Decimal('20'))

    def test_pagos_vencidos_respeta_plazo_saldo_y_estado_sin_inventar_vencimiento_mora(self):
        ahora = timezone.now()
        limite = ahora - timedelta(days=5)
        justo = self.crear_solicitud(estado='Aprobada', fecha_revision=limite)
        parcial = self.crear_solicitud(estado='Vencida', fecha_revision=limite - timedelta(days=1))
        self.pago(parcial.presupuesto, 'renta', '250')
        self.crear_solicitud(estado='Aprobada', fecha_revision=limite + timedelta(microseconds=1))
        self.crear_solicitud(estado='Aprobada')  # Sin fecha de revisión: no hay plazo conocido.
        for estado in ('Pendiente', 'Rechazada'):
            self.crear_solicitud(estado=estado, fecha_revision=limite)
        pagada = self.crear_solicitud(estado='Aprobada', fecha_revision=limite, politica_mora_aplica=False)
        self.completar_pago_inicial(pagada)
        pagada.presupuesto.mora_total = Decimal('100')
        pagada.presupuesto.save()
        self.crear_entrega(unidad=self.unidad_adicional(), fecha_revision=limite - timedelta(days=10))
        with patch('apps.cuentas.views.timezone.now', return_value=ahora):
            respuesta = self.panel()
            listado = self.client.get(reverse('ventas:presupuesto_lista') + '?vencidos=1')
        self.assertEqual(respuesta.context['pagos_vencidos_total'], 2)
        self.assertEqual([p.pk for p in respuesta.context['pagos_vencidos']], [parcial.presupuesto.pk, justo.presupuesto.pk])
        self.assertEqual(list(listado.context['presupuestos']), list(respuesta.context['pagos_vencidos']))
        self.assertContains(respuesta, 'RD$3500.00')
        self.assertContains(respuesta, 'RD$3750.00')
        for p in respuesta.context['pagos_vencidos']:
            url = reverse('ventas:presupuesto_detalle', args=[p.pk])
            self.assertContains(respuesta, url)
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_bandejas_limitan_a_cinco_con_totales_y_enlaces_a_listados_completos(self):
        pendientes = [self.crear_solicitud() for _ in range(7)]
        for _ in range(7):
            self.mantenimiento()
            self.crear_solicitud(estado='Vencida', fecha_revision=timezone.now() - timedelta(days=6))
        respuesta = self.panel()
        self.assertEqual(respuesta.context['kpis']['solicitudes_pendientes'], 7)
        self.assertEqual(respuesta.context['mantenimientos_atencion_total'], 7)
        self.assertEqual(respuesta.context['pagos_vencidos_total'], 7)
        for nombre in ('solicitudes_pendientes', 'mantenimientos_atencion', 'pagos_vencidos'):
            self.assertEqual(len(respuesta.context[nombre]), 5)
        for s in pendientes[:5]:
            url = reverse('alquileres:solicitud_detalle', args=[s.pk])
            self.assertContains(respuesta, url)
            self.assertEqual(self.client.get(url).status_code, 200)
        solicitudes_url = reverse('alquileres:solicitud_lista') + '?estado=Pendiente'
        mantenimiento_url = reverse('mantenimiento:mantenimiento_lista') + '?atencion=1'
        pagos_url = reverse('ventas:presupuesto_lista') + '?vencidos=1'
        for url in (solicitudes_url, mantenimiento_url, pagos_url):
            self.assertContains(respuesta, url)
        self.assertEqual(len(self.client.get(solicitudes_url).context['solicitudes']), 7)
        self.assertEqual(len(self.client.get(mantenimiento_url).context['mantenimientos']), 7)
        self.assertEqual(len(self.client.get(pagos_url).context['presupuestos']), 7)

    def test_listado_vencidos_conserva_filtro_al_paginar(self):
        for _ in range(26):
            self.crear_solicitud(estado='Vencida', fecha_revision=timezone.now() - timedelta(days=6))
        url = reverse('ventas:presupuesto_lista') + '?vencidos=1'
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.context['paginator'].count, 26)
        self.assertContains(respuesta, '?vencidos=1&amp;page=2')
        self.assertEqual(len(self.client.get(url + '&page=2').context['presupuestos']), 1)

    def test_cliente_no_recibe_indicadores_globales_ni_listados_de_gestion(self):
        self.crear_solicitud(cliente=self.otro, comentario='Solicitud ajena de prueba')
        self.client.force_login(self.cliente)
        respuesta = self.panel()
        self.assertNotIn('kpis', respuesta.context)
        self.assertNotContains(respuesta, 'Solicitud ajena de prueba')
        for url in (reverse('ventas:presupuesto_lista') + '?vencidos=1',
                    reverse('mantenimiento:mantenimiento_lista') + '?atencion=1'):
            self.assertEqual(self.client.get(url).status_code, 403)
