from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.inventario.models import Maquinaria, Unidad
from .models import SolicitudAlquiler
from .tests_datos import DatosIntegracion


class SugerenciasCodigosTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def setUp(self):
        self.client.force_login(self.admin)
        self.url = reverse('alquileres:solicitud_codigos')
        self.lista = reverse('alquileres:solicitud_lista')
        self.solicitudes = {}
        for numero in range(1, 4):
            unidad = self.crear_equipo(f'EXC-PR-00{numero}')
            self.solicitudes[numero] = self.crear_solicitud(unidad=unidad)
        self.otra_del_equipo = self.crear_solicitud(unidad=self.solicitudes[2].unidad, cliente=self.otro)
        self.crear_equipo('EXC-PR-004')  # Sin solicitudes: nunca debe sugerirse.

    def crear_equipo(self, codigo, nombre='Excavadora de prueba'):
        maquinaria = Maquinaria.objects.create(
            codigo=codigo, nombre=nombre, categoria=self.maquinaria.categoria,
            costo_adquisicion=10000, tarifa_diaria=750, tarifa_semanal=4500,
            tarifa_mensual=15000, deposito_garantia=3000,
        )
        return Unidad.objects.create(maquinaria=maquinaria, numero_serie=codigo, ubicacion_actual='Obra de prueba')

    def test_prefijo_sin_mayusculas_no_duplica_y_no_incluye_equipos_sin_solicitudes(self):
        self.assertEqual(self.client.get(self.url, {'q': 'exc-pr-00'}).json(), {
            'codigos': ['EXC-PR-001', 'EXC-PR-002', 'EXC-PR-003'],
        })

    def test_codigo_completo_deja_solo_la_coincidencia_exacta(self):
        ampliado = self.crear_equipo('EXC-PR-002-A')
        self.crear_solicitud(unidad=ampliado)
        self.assertEqual(self.client.get(self.url, {'q': 'exc-pr-002'}).json()['codigos'], ['EXC-PR-002'])

    def test_sugerencias_no_se_recortan_a_cinco(self):
        for numero in range(5, 13):
            self.crear_solicitud(unidad=self.crear_equipo(f'EXC-PR-{numero:03}'))
        self.assertEqual(len(self.client.get(self.url, {'q': 'EXC-PR-0'}).json()['codigos']), 11)

    def test_sugerencias_respetan_estado_y_periodo_inclusivo(self):
        solicitud = self.solicitudes[2]
        solicitud.estado = 'Aprobada'
        solicitud.fecha_fin += timedelta(days=4)
        solicitud.save()
        filtros = {'q': 'EXC-PR-00', 'estado': 'Aprobada',
                   'desde': solicitud.fecha_fin.isoformat(), 'hasta': solicitud.fecha_fin.isoformat()}
        self.assertEqual(self.client.get(self.url, filtros).json()['codigos'], ['EXC-PR-002'])
        filtros['desde'] = (solicitud.fecha_fin + timedelta(days=1)).isoformat()
        filtros['hasta'] = filtros['desde']
        self.assertEqual(self.client.get(self.url, filtros).json()['codigos'], [])

    def test_seleccion_exacta_incluye_todas_las_solicitudes_del_equipo_y_conserva_filtros(self):
        intrusa = self.crear_solicitud(unidad=self.crear_equipo('OTRO-CODIGO', nombre='Equipo EXC-PR-002'))
        filtros = {'q': 'EXC-PR-002', 'codigo_exacto': 'EXC-PR-002', 'estado': 'Pendiente',
                   'desde': timezone.localdate().isoformat(), 'hasta': timezone.localdate().isoformat()}
        respuesta = self.client.get(self.lista, filtros)
        self.assertEqual(set(respuesta.context['solicitudes']), {self.solicitudes[2], self.otra_del_equipo})
        for clave, valor in filtros.items():
            self.assertEqual(respuesta.context['filtros'][clave].value(), valor)
        filtros['codigo_exacto'] = ''
        self.assertIn(intrusa, self.client.get(self.lista, filtros).context['solicitudes'])

    def test_editar_busqueda_descarta_seleccion_anterior_y_conserva_busqueda_libre(self):
        for consulta in (self.cliente.email, 'Ana', 'Excavadora de prueba', self.solicitudes[1].unidad.numero_serie,
                         f'#{self.solicitudes[1].pk}'):
            respuesta = self.client.get(self.lista, {'q': consulta, 'codigo_exacto': 'EXC-PR-002'})
            self.assertIn(self.solicitudes[1], respuesta.context['solicitudes'])
            self.assertEqual(respuesta.context['filtros'].cleaned_data['codigo_exacto'], '')

    def test_acceso_restringido_y_filtros_invalidos_no_exponen_codigos(self):
        self.assertEqual(self.client.get(self.url, {'q': ''}).json()['codigos'], [])
        for datos in ({'q': 'EXC', 'estado': 'inventado'}, {'q': 'EXC', 'desde': 'incorrecta'}, {'q': 'x' * 201}):
            respuesta = self.client.get(self.url, datos)
            self.assertEqual(respuesta.status_code, 400)
            self.assertEqual(respuesta.json()['codigos'], [])
        self.assertEqual(self.client.post(self.url, {'q': 'EXC'}).status_code, 405)
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url, {'q': 'EXC'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {'q': 'EXC'}).status_code, 302)
