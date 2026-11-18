from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.alquileres.models import SolicitudAlquiler
from apps.cierre_mensual.consultas import (
    ingresos_periodo_actual,
    semanas_del_mes,
)
from apps.cierre_mensual.models import CierreMensual
from apps.cierre_mensual.servicios import cerrar_periodo
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from apps.cuentas.models import RolUsuario, UsuarioPersonalizado


class CierreMensualTests(TestCase):
    def setUp(self):
        self.administrador = UsuarioPersonalizado.objects.create_user(
            email='admin-cierre@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
            first_name='Admin',
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-cierre@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Cierre mensual')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='CIERRE-01',
            nombre='Equipo de prueba',
            costo_adquisicion=Decimal('1000.00'),
            tarifa_diaria=Decimal('100.00'),
            tarifa_semanal=Decimal('500.00'),
            tarifa_mensual=Decimal('1500.00'),
            deposito_garantia=Decimal('100.00'),
        )
        unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='CIERRE-SERIE-01',
        )
        hoy = timezone.localdate()
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=unidad,
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=1),
            politica_mora_aplica=False,
        )
        self.presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=solicitud,
            tarifa_periodo=Decimal('100.00'),
            importe_renta=Decimal('100.00'),
            deposito_garantia=Decimal('100.00'),
            mora_total=Decimal('100.00'),
        )
        self.inicio = timezone.now() - timedelta(hours=1)
        CierreMensual.objects.filter(activo=True).update(inicio_periodo=self.inicio)
        self.periodo = CierreMensual.objects.get(activo=True)

    def crear_pago(self, monto, concepto, creado_en):
        return PagoAlquiler.objects.create(
            presupuesto=self.presupuesto,
            monto=Decimal(monto),
            concepto=concepto,
            metodo='efectivo',
            referencia=f'{concepto}-{creado_en.timestamp()}',
            registrado_por=self.administrador,
            creado_en=creado_en,
        )

    def test_ingresos_consulta_pagos_del_periodo_y_refleja_ediciones(self):
        self.crear_pago('10.00', 'renta', self.inicio - timedelta(seconds=1))
        renta = self.crear_pago('20.00', 'renta', self.inicio + timedelta(seconds=1))
        self.crear_pago('5.00', 'mora', self.inicio + timedelta(seconds=2))
        self.crear_pago('30.00', 'deposito', self.inicio + timedelta(seconds=3))

        self.assertEqual(ingresos_periodo_actual(), Decimal('25.00'))

        renta.monto = Decimal('24.00')
        renta.save()
        self.assertEqual(ingresos_periodo_actual(), Decimal('29.00'))

    def test_cierre_exporta_periodo_inicia_otro_y_conserva_los_pagos(self):
        self.crear_pago('20.00', 'renta', self.inicio + timedelta(seconds=1))
        self.crear_pago('5.00', 'mora', self.inicio + timedelta(seconds=2))
        self.crear_pago('30.00', 'deposito', self.inicio + timedelta(seconds=3))

        resultado = cerrar_periodo()
        self.periodo.refresh_from_db()
        nuevo_periodo = CierreMensual.objects.get(activo=True)

        self.assertFalse(self.periodo.activo)
        self.assertEqual(self.periodo.origen, 'manual')
        self.assertEqual(nuevo_periodo.inicio_periodo, self.periodo.cerrado_en)
        self.assertEqual(resultado.cantidad_pagos, 2)
        self.assertEqual(resultado.total, Decimal('25.00'))
        self.assertEqual(PagoAlquiler.objects.count(), 3)
        self.assertEqual(ingresos_periodo_actual(), Decimal('0.00'))

        hoja = load_workbook(BytesIO(resultado.contenido), data_only=True).active
        self.assertEqual(hoja['L4'].value, 'Total ingresos')
        self.assertEqual(hoja['M4'].value, 25)

    def test_dashboard_muestra_ingresos_actuales_y_boton_solo_al_administrador(self):
        self.crear_pago('20.00', 'renta', self.inicio + timedelta(seconds=1))

        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('cuentas:dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'RD$20.00')
        self.assertNotContains(respuesta, 'Cerrar mes y descargar Excel')

        self.client.force_login(self.cliente)
        respuesta = self.client.get(reverse('cuentas:dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Cerrar mes y descargar Excel')

    def test_boton_e_historial_estan_dentro_de_ventas_y_presupuestos(self):
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('ventas:presupuesto_lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Cerrar mes y descargar Excel')
        self.assertContains(respuesta, reverse('cierre_mensual:historial'))

    def test_historial_mensual_muestra_periodos_y_solo_es_administrativo(self):
        hoy = timezone.localdate()
        self.client.force_login(self.administrador)
        respuesta = self.client.get(reverse('cierre_mensual:historial'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            reverse(
                'cierre_mensual:mes',
                kwargs={'anio': hoy.year, 'mes': hoy.month},
            ),
        )

        self.client.force_login(self.cliente)
        respuesta = self.client.get(reverse('cierre_mensual:historial'))
        self.assertEqual(respuesta.status_code, 403)

    def test_historial_crea_cuatro_secciones_de_semana_por_mes(self):
        self.client.force_login(self.administrador)
        hoy = timezone.localdate()
        respuesta = self.client.get(reverse(
            'cierre_mensual:mes',
            kwargs={'anio': hoy.year, 'mes': hoy.month},
        ))

        self.assertEqual(respuesta.status_code, 200)
        semanas = semanas_del_mes(hoy.year, hoy.month)
        ultimo_dia = (
            (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)
            - timedelta(days=1)
        ).day
        self.assertEqual(
            [(semana['desde'].day, semana['hasta'].day) for semana in semanas],
            [(1, 7), (8, 14), (15, 21), (22, ultimo_dia)],
        )
        for numero in range(1, 5):
            self.assertContains(respuesta, f'Semana {numero}')

    def test_detalle_semanal_muestra_todos_los_conceptos_y_datos_del_pago(self):
        pago = self.crear_pago('30.00', 'deposito', timezone.now())
        self.client.force_login(self.administrador)
        hoy = timezone.localtime(pago.creado_en).date()
        semana = min((hoy.day - 1) // 7 + 1, 4)
        respuesta = self.client.get(reverse(
            'cierre_mensual:semana',
            kwargs={'anio': hoy.year, 'mes': hoy.month, 'semana': semana},
        ))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.cliente.email)
        self.assertContains(respuesta, 'CIERRE-01')
        self.assertContains(respuesta, 'Depósito de garantía')
        self.assertContains(respuesta, '30.00')

    def test_solo_administrador_puede_descargar_y_cerrar(self):
        self.client.force_login(self.cliente)
        respuesta = self.client.post(reverse('cierre_mensual:cerrar_mes'))
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(CierreMensual.objects.get(activo=True).pk, self.periodo.pk)

        self.client.force_login(self.administrador)
        respuesta = self.client.post(reverse('cierre_mensual:cerrar_mes'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment;', respuesta['Content-Disposition'])
        self.assertEqual(CierreMensual.objects.filter(activo=True).count(), 1)

    def test_comando_automatico_guarda_excel_y_no_duplica_el_cierre_del_dia(self):
        hoy = timezone.localdate()
        inicio_mes_siguiente = (hoy.replace(day=28) + timedelta(days=4)).replace(day=1)
        ultimo_dia = inicio_mes_siguiente - timedelta(days=1)
        cierre = timezone.make_aware(
            datetime.combine(ultimo_dia, time(23, 59)),
            timezone.get_current_timezone(),
        )
        with TemporaryDirectory() as directorio:
            with override_settings(MEDIA_ROOT=directorio):
                with patch(
                    'django.utils.timezone.localdate',
                    return_value=ultimo_dia,
                ), patch(
                    'django.utils.timezone.now',
                    return_value=cierre,
                ):
                    call_command('cerrar_mes', verbosity=0)
                    call_command('cerrar_mes', verbosity=0)

                self.periodo.refresh_from_db()
                self.assertEqual(self.periodo.origen, 'automatico')
                self.assertTrue(
                    self.periodo.archivo_excel.startswith('cierres_mensuales/')
                )
                self.assertTrue(default_storage.exists(self.periodo.archivo_excel))
                self.assertEqual(
                    CierreMensual.objects.filter(origen='automatico').count(),
                    1,
                )
