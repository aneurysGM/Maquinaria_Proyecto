from datetime import date, datetime, timedelta, timezone as tz
from decimal import Decimal
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.alquileres.models import SolicitudAlquiler
from apps.alquileres.tests_datos import DatosIntegracion
from apps.inventario.models import Unidad
from apps.mantenimiento.models import Mantenimiento
from .exportacion_excel import exportar_excel


class ReportesIntegracionTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def setUp(self):
        self.client.force_login(self.superadmin)
        self.otra_unidad = Unidad.objects.create(
            maquinaria=self.maquinaria, numero_serie='OTRA-SERIE',
            ubicacion_actual='Santiago', activo=False,
        )
        salida = datetime(2026, 11, 10, 3, 30, tzinfo=tz.utc)  # 9/11 23:30 local
        self.devuelta = self.crear_solicitud(
            estado='Aprobada', fecha_inicio=date(2026, 11, 1), fecha_fin=date(2026, 11, 9),
            fecha_salida=salida, entregado_por=self.admin,
            fecha_retorno=salida + timedelta(hours=10), recibido_por=self.superadmin,
        )
        self.pendiente = self.crear_solicitud(
            unidad=self.otra_unidad, cliente=self.otro, estado='Aprobada',
            fecha_inicio=date(2026, 11, 10), fecha_fin=date(2026, 11, 12),
            fecha_salida=datetime(2026, 11, 10, 4, 15, tzinfo=tz.utc), entregado_por=self.admin,
        )
        self.sin_salida = self.crear_solicitud(
            fecha_inicio=date(2026, 11, 20), fecha_fin=date(2026, 11, 21),
        )
        self.mantenimiento = Mantenimiento.objects.create(
            unidad=self.unidad, fecha=date(2026, 11, 9), tipo='Preventivo',
            descripcion='=Texto literal\nRevisión de equipo', costo=Decimal('123.45'), tecnico=self.tecnico,
        )
        Mantenimiento.objects.create(
            unidad=self.otra_unidad, fecha=date(2026, 11, 10), tipo='Correctivo',
            descripcion='Otro trabajo', costo=Decimal('900.00'), tecnico=self.tecnico,
        )

    def url(self, tipo):
        return reverse('reportes:reporte', args=[tipo])

    def libro(self, respuesta):
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('spreadsheetml.sheet', respuesta['Content-Type'])
        return load_workbook(BytesIO(respuesta.content))

    def test_apertura_inicial_cuatro_reportes_sin_error(self):
        for tipo in ('maquinaria', 'solicitudes', 'entregas', 'mantenimientos'):
            with self.subTest(tipo=tipo):
                respuesta = self.client.get(self.url(tipo))
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(respuesta.context['form'].is_bound)
                self.assertContains(respuesta, 'name="consultar" value="1"')
                self.assertNotContains(respuesta, 'Revisa los filtros indicados')

    def test_consulta_sin_filtros_y_exportacion_son_posibles(self):
        for tipo in ('maquinaria', 'solicitudes', 'entregas', 'mantenimientos'):
            respuesta = self.client.get(self.url(tipo), {'consultar': '1'})
            self.assertTrue(respuesta.context['filtrado_valido'])
            self.assertTrue(respuesta.context['filas'])
            self.libro(self.client.get(respuesta.context['exportar_excel_url'])).close()

    def test_solo_superusuario_accede_a_pantallas_y_descargas(self):
        for usuario in (self.admin, self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse('reportes:indice')).status_code, 403)
            for tipo in ('maquinaria', 'solicitudes', 'entregas', 'mantenimientos'):
                for datos in ({}, {'formato': 'xlsx'}):
                    self.assertEqual(self.client.get(self.url(tipo), datos).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url('entregas')).status_code, 302)

    def test_filas_y_filtros_de_pantalla_coinciden_con_los_cuatro_xlsx(self):
        casos = {
            'maquinaria': {'q': '0000456', 'estado': 'Disponible'},
            'solicitudes': {'cliente': str(self.cliente.pk), 'estado': 'Aprobada', 'desde': '2026-11-09', 'hasta': '2026-11-09'},
            'entregas': {'situacion': 'devuelta', 'desde': '2026-11-09', 'hasta': '2026-11-09'},
            'mantenimientos': {'unidad': str(self.unidad.pk), 'tipo': 'Preventivo', 'desde': '2026-11-09', 'hasta': '2026-11-09'},
        }
        for tipo, filtros in casos.items():
            with self.subTest(tipo=tipo):
                respuesta = self.client.get(self.url(tipo), filtros)
                self.assertEqual(respuesta.status_code, 200)
                enlace = respuesta.context['exportar_excel_url']
                self.assertEqual(parse_qs(urlsplit(enlace).query), {**{k: [v] for k, v in filtros.items()}, 'formato': ['xlsx']})
                libro = self.libro(self.client.get(enlace))
                hoja = libro.active
                filas = respuesta.context['filas']
                self.assertEqual(len(filas), 1)
                self.assertEqual([c.value for c in hoja[1]], list(respuesta.context['encabezados']))
                for columna, esperado in enumerate(filas[0], 1):
                    if isinstance(esperado, datetime):
                        esperado = esperado.replace(tzinfo=None)
                    elif isinstance(esperado, date):
                        esperado = datetime.combine(esperado, datetime.min.time())
                    elif isinstance(esperado, Decimal):
                        esperado = float(esperado)
                    self.assertEqual(hoja.cell(2, columna).value, esperado)
                self.assertEqual(hoja.auto_filter.ref, f'A1:{hoja.cell(1, len(filas[0])).column_letter}2')
                self.assertEqual(hoja.freeze_panes, 'A2')
                libro.close()

    def test_entregas_fechas_nativas_ordenables_y_limite_local(self):
        respuesta = self.client.get(self.url('entregas'), {'desde': '2026-11-09', 'hasta': '2026-11-09', 'formato': 'xlsx'})
        libro = self.libro(respuesta)
        hoja = libro.active
        self.assertEqual(hoja.max_row, 2)
        self.assertEqual(hoja['A2'].value, str(self.devuelta.pk))
        for coordenada in ('D2', 'E2'):
            self.assertEqual(hoja[coordenada].data_type, 'd')
            self.assertIsInstance(hoja[coordenada].value, datetime)
            self.assertIsNone(hoja[coordenada].value.tzinfo)
        self.assertEqual(hoja['D2'].value, datetime(2026, 11, 9, 23, 30))
        libro.close()

    def test_situaciones_y_resultados_vacios_no_inventan_entregas(self):
        for situacion, solicitud in [('pendiente', self.pendiente), ('devuelta', self.devuelta)]:
            respuesta = self.client.get(self.url('entregas'), {'situacion': situacion})
            self.assertEqual([fila[0] for fila in respuesta.context['filas']], [str(solicitud.pk)])
        respuesta = self.client.get(self.url('maquinaria'), {'q': 'sin-coincidencias', 'formato': 'xlsx'})
        libro = self.libro(respuesta)
        self.assertEqual(libro.active.max_row, 1)
        libro.close()

    def test_mantenimiento_total_y_texto_literal(self):
        respuesta = self.client.get(self.url('mantenimientos'), {'unidad': self.unidad.pk, 'formato': 'xlsx'})
        libro = self.libro(respuesta)
        hoja = libro.active
        self.assertEqual(hoja['D2'].data_type, 's')
        self.assertEqual(hoja['D2'].value, self.mantenimiento.descripcion)
        self.assertEqual(hoja['F2'].value, 123.45)
        self.assertEqual(hoja['F3'].value, 123.45)
        self.assertEqual(hoja.auto_filter.ref, 'A1:F2')
        libro.close()

    def test_filtros_invalidos_no_exportan_csv_410_y_tipo_404(self):
        for datos in ({'desde': 'no-fecha'}, {'desde': '2026-11-10', 'hasta': '2026-11-09'}, {'situacion': 'inventado'}, {'formato': 'pdf'}):
            respuesta = self.client.get(self.url('entregas'), {**datos, 'formato': datos.get('formato', 'xlsx')})
            self.assertEqual(respuesta.status_code, 400)
            self.assertNotIn('Content-Disposition', respuesta)
        self.assertEqual(self.client.get(self.url('entregas'), {'formato': 'csv'}).status_code, 410)
        self.assertEqual(self.client.get(self.url('no-existe')).status_code, 404)

    def test_cliente_historico_sigue_filtrable_y_reportes_no_escriben(self):
        self.cliente.is_active = False
        self.cliente.rol = ''
        self.cliente.save(update_fields=['is_active', 'rol'])
        antes = list(SolicitudAlquiler.objects.order_by('pk').values())
        unidades = list(Unidad.objects.order_by('pk').values())
        for tipo in ('maquinaria', 'solicitudes', 'entregas', 'mantenimientos'):
            respuesta = self.client.get(self.url(tipo), {'consultar': '1'})
            if tipo == 'solicitudes':
                self.assertIn(self.cliente, respuesta.context['form'].fields['cliente'].queryset)
            self.client.get(respuesta.context['exportar_excel_url'])
        self.assertEqual(list(SolicitudAlquiler.objects.order_by('pk').values()), antes)
        self.assertEqual(list(Unidad.objects.order_by('pk').values()), unidades)


class ExcelLiteralTests(SimpleTestCase):
    def test_identificadores_formulas_precision_y_fechas_antiguas(self):
        respuesta = exportar_excel('prueba', 'Prueba', ('Serie', 'Texto', 'Costo', 'Fecha'), [
            ('0000456', '=SUM(A1:A2)', Decimal('1234567890123456.78'), date(1800, 1, 1)),
            ('#REF!', '+texto', Decimal('10000000000000.00'), date(2026, 11, 9)),
        ], None)
        libro = load_workbook(BytesIO(respuesta.content))
        hoja = libro.active
        self.assertEqual(hoja['A2'].value, '0000456')
        self.assertEqual(hoja['B2'].data_type, 's')
        self.assertEqual(hoja['C2'].value, '1234567890123456.78')
        self.assertEqual(hoja['D2'].value, '1800-01-01')
        self.assertEqual(hoja['A3'].data_type, 's')
        self.assertEqual(hoja['C3'].data_type, 'n')
        self.assertEqual(hoja['D3'].data_type, 'd')
        libro.close()
