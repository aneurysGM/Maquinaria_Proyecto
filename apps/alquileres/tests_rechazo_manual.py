"""Rechazo manual con solicitudes ficticias en la base temporal de pruebas."""
from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from .models import SolicitudAlquiler
from .tests_datos import DatosIntegracion


class ControlesRechazo(HTMLParser):
    """Localiza controles y su ventana sin depender del formato del HTML."""
    def __init__(self, html):
        super().__init__()
        self.pila = []
        self.controles = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag in ('button', 'textarea'):
            self.controles.append({'tag': tag, 'attrs': atributos, 'texto': '',
                                   'ventanas': [a.get('id') for _, a in self.pila if 'modal' in a.get('class', '').split()]})
        if tag not in ('input', 'br', 'hr', 'img', 'link', 'meta'):
            self.pila.append((tag, atributos))

    def handle_endtag(self, tag):
        for indice in range(len(self.pila) - 1, -1, -1):
            if self.pila[indice][0] == tag:
                del self.pila[indice:]
                break

    def handle_data(self, data):
        if self.pila and self.pila[-1][0] == 'button':
            self.controles[-1]['texto'] += data.strip()


class RechazoManualTests(DatosIntegracion, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crear_datos()

    def setUp(self):
        self.solicitud = self.crear_solicitud(comentario='Comentario del cliente de prueba')
        self.url = reverse('alquileres:solicitud_resolver', args=[self.solicitud.pk])
        self.client.force_login(self.admin)

    def test_lista_y_detalle_solo_piden_motivo_dentro_de_la_ventana(self):
        otra = self.crear_solicitud(cliente=self.otro)
        for url in (reverse('alquileres:solicitud_lista'), reverse('alquileres:solicitud_detalle', args=[self.solicitud.pk])):
            with self.subTest(url=url):
                respuesta = self.client.get(url)
                controles = ControlesRechazo(respuesta.content.decode()).controles
                botones = [c for c in controles if c['tag'] == 'button']
                aprobar = next(c for c in botones if c['texto'] == 'Aprobar')
                abrir = next(c for c in botones if c['texto'] == 'Rechazar solicitud'
                             and c['attrs'].get('data-bs-target') == f'#rechazar-solicitud-{self.solicitud.pk}')
                self.assertLess(controles.index(aprobar), controles.index(abrir))
                self.assertIn('btn-success', aprobar['attrs']['class'])
                self.assertEqual(abrir['attrs']['type'], 'button')
                self.assertIn('btn-danger', abrir['attrs']['class'])
                self.assertEqual(abrir['attrs']['data-bs-target'], f'#rechazar-solicitud-{self.solicitud.pk}')
                for campo in (c for c in controles if c['tag'] == 'textarea' and c['attrs'].get('name') == 'motivo_rechazo'):
                    self.assertEqual(campo['ventanas'], [f"rechazar-solicitud-{campo['attrs']['id'].removeprefix('motivo-')}"])
                    self.assertIn('required', campo['attrs'])
                self.assertContains(respuesta, f'Rechazar solicitud #{self.solicitud.pk}')
                self.assertContains(respuesta, 'Motivo:')
                self.assertContains(respuesta, 'El cliente podrá leer el motivo en <strong>Mis alquileres</strong>.', html=True)
        lista = self.client.get(reverse('alquileres:solicitud_lista'))
        self.assertContains(lista, f'id="rechazar-solicitud-{otra.pk}"', count=1)

    def test_cancelar_y_cerrar_son_controles_locales_y_no_guardan_rechazo(self):
        antes = SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk)
        respuesta = self.client.get(reverse('alquileres:solicitud_detalle', args=[self.solicitud.pk]))
        controles = ControlesRechazo(respuesta.content.decode()).controles
        cancelar = next(c for c in controles if c['texto'] == 'Cancelar')
        cerrar = next(c for c in controles if c['attrs'].get('aria-label') == 'Cerrar' and c['ventanas'])
        for control in (cancelar, cerrar):
            self.assertEqual(control['attrs']['type'], 'button')
            self.assertEqual(control['attrs']['data-bs-dismiss'], 'modal')
        confirmar = next(c for c in controles if c['texto'] == 'Confirmar rechazo')
        self.assertEqual(confirmar['attrs']['type'], 'submit')
        self.client.get(self.url)  # Abrir una dirección nunca confirma el rechazo.
        self.assertEqual(SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk), antes)

    def test_servidor_rechaza_motivo_ausente_vacio_o_demasiado_largo(self):
        antes = SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk)
        for motivo in (None, '', ' \n\t ', 'x' * 1001):
            with self.subTest(motivo=motivo):
                datos = {'decision': 'Rechazada'}
                if motivo is not None:
                    datos['motivo_rechazo'] = motivo
                respuesta = self.client.post(self.url, datos, follow=True)
                self.assertContains(respuesta, 'Escribe un motivo de rechazo')
                self.assertEqual(SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk), antes)

    def test_ventana_abierta_antes_de_aprobar_no_puede_rechazar_la_aprobada(self):
        self.client.get(reverse('alquileres:solicitud_detalle', args=[self.solicitud.pk]))
        self.client.post(self.url, {'decision': 'Aprobada'})
        aprobada = SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk)
        self.assertEqual(aprobada['estado'], 'Aprobada')
        respuesta = self.client.post(self.url, {'decision': 'Rechazada', 'motivo_rechazo': 'Motivo desactualizado'}, follow=True)
        self.assertContains(respuesta, 'ya había sido revisada')
        self.assertEqual(SolicitudAlquiler.objects.values().get(pk=self.solicitud.pk), aprobada)

    def test_confirmar_guarda_motivo_y_cliente_lo_lee_sin_cambiar_otras_solicitudes(self):
        otra = self.crear_solicitud(cliente=self.otro)
        antes = SolicitudAlquiler.objects.values().get(pk=otra.pk)
        motivo = 'No se puede atender la ubicación indicada en esta solicitud de prueba.'
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(self.url, {'decision': 'Rechazada', 'motivo_rechazo': f'  {motivo}  '}, follow=True)
        self.assertEqual(respuesta.status_code, 200)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'Rechazada')
        self.assertEqual(self.solicitud.motivo_rechazo, motivo)
        self.assertEqual(self.solicitud.comentario, 'Comentario del cliente de prueba')
        self.assertEqual(self.solicitud.revisado_por, self.admin)
        self.assertIsNotNone(self.solicitud.fecha_revision)
        self.assertEqual(SolicitudAlquiler.objects.values().get(pk=otra.pk), antes)
        self.client.force_login(self.cliente)
        detalle = self.client.get(reverse('alquileres:solicitud_detalle', args=[self.solicitud.pk]))
        self.assertContains(detalle, f'<p><strong>Motivo:</strong><br>{motivo}</p>', html=True)
        self.assertContains(self.client.get(reverse('alquileres:solicitud_lista')), 'Ver motivo')
        self.assertNotContains(detalle, 'Rechazar solicitud')

    def test_cliente_y_tecnico_no_pueden_confirmar_rechazos(self):
        for usuario in (self.cliente, self.tecnico):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(self.url, {'decision': 'Rechazada', 'motivo_rechazo': 'Sin autorización'}).status_code, 403)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'Pendiente')
