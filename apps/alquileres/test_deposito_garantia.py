from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from .models import SolicitudAlquiler


class DepositoGarantiaAutomaticoTests(TestCase):
    def setUp(self):
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='deposito@example.com',
            password='pass',
            rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Depósitos automáticos')
        self.maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='DEP-01',
            nombre='Máquina de prueba',
            costo_adquisicion=Decimal('5070000.00'),
            tarifa_diaria=Decimal('1000.00'),
            tarifa_semanal=Decimal('6000.00'),
            tarifa_mensual=Decimal('20000.00'),
            deposito_garantia=Decimal('1.00'),
        )
        self.unidad = Unidad.objects.create(
            maquinaria=self.maquinaria,
            numero_serie='DEP-SERIE-01',
        )
        self.client.force_login(self.cliente)

    def test_calcula_factor_y_redondea_a_dos_decimales(self):
        esperados = {
            1: Decimal('405600.00'),
            7: Decimal('405600.00'),
            8: Decimal('344760.00'),
            29: Decimal('344760.00'),
            30: Decimal('304200.00'),
        }
        for dias, esperado in esperados.items():
            with self.subTest(dias=dias):
                self.assertEqual(
                    self.maquinaria.calcular_deposito_garantia(dias),
                    esperado,
                )

    def test_valor_ingresado_como_deposito_manual_se_ignora(self):
        self.maquinaria.refresh_from_db()
        self.assertEqual(
            self.maquinaria.deposito_garantia,
            Decimal('405600.00'),
        )

    def test_solicitud_guarda_el_deposito_segun_su_duracion(self):
        fecha_inicio = timezone.localdate() + timedelta(days=1)

        respuesta = self.client.post(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
            {
                'fecha_inicio': fecha_inicio.isoformat(),
                'plan': 'mensual',
                'cantidad': '1',
                'comentario': '',
            },
        )

        solicitud = SolicitudAlquiler.objects.get(unidad=self.unidad)
        self.assertRedirects(
            respuesta,
            reverse('ventas:presupuesto_detalle', args=[solicitud.presupuesto.pk]),
        )
        self.assertEqual(
            solicitud.presupuesto.deposito_garantia,
            Decimal('304200.00'),
        )
