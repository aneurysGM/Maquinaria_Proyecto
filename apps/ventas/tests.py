from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.alquileres.models import SolicitudAlquiler
from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from .models import PagoAlquiler, PresupuestoAlquiler


class PresupuestosAlquilerTests(TestCase):
    def setUp(self):
        self.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-ventas@example.com',
            password='test-password',
            rol=RolUsuario.ADMINISTRADOR,
        )
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-ventas@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        categoria, _ = Categoria.objects.get_or_create(nombre='Excavadoras')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='VEN-001',
            nombre='Excavadora para presupuesto',
            descripcion='Equipo de pruebas.',
            costo_adquisicion=90000,
            tarifa_diaria=500,
            tarifa_semanal=700,
            tarifa_mensual=3000,
            deposito_garantia=1000,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SERIE-VEN-001',
            ubicacion_actual='Santo Domingo',
        )
        self.solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            fecha_inicio=timezone.localdate() + timedelta(days=1),
            fecha_fin=timezone.localdate() + timedelta(days=7),
            plan='semanal',
            cantidad=1,
            estado='Aprobada',
        )
        self.presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=self.solicitud,
            tarifa_periodo=700,
            importe_renta=700,
            deposito_garantia=1000,
        )

    def test_cliente_consulta_su_presupuesto_pero_no_el_de_otra_cuenta(self):
        self.client.force_login(self.cliente)

        respuesta = self.client.get(
            reverse(
                'ventas:presupuesto_detalle',
                args=[self.presupuesto.pk],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Depósito reembolsable')
        self.assertContains(respuesta, 'Saldo pendiente')

        otro = UsuarioPersonalizado.objects.create_user(
            email='otro-ventas@example.com',
            password='test-password',
            rol=RolUsuario.CLIENTE,
        )
        self.client.force_login(otro)
        respuesta_ajena = self.client.get(
            reverse(
                'ventas:presupuesto_detalle',
                args=[self.presupuesto.pk],
            )
        )
        self.assertEqual(respuesta_ajena.status_code, 404)

    def test_admin_registra_pago_y_el_saldo_se_actualiza(self):
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse('ventas:pago_registrar', args=[self.presupuesto.pk]),
            {
                'concepto': 'renta',
                'monto': '500.00',
                'metodo': 'transferencia',
                'referencia': 'TR-1',
            },
        )

        self.assertRedirects(
            respuesta,
            reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk]),
        )
        self.assertEqual(PagoAlquiler.objects.count(), 1)
        self.assertEqual(self.presupuesto.total_pagado, Decimal('500.00'))
        self.assertEqual(self.presupuesto.saldo_pendiente, Decimal('1200.00'))

    def test_pago_no_puede_superar_el_saldo(self):
        self.client.force_login(self.admin)

        self.client.post(
            reverse('ventas:pago_registrar', args=[self.presupuesto.pk]),
            {
                'concepto': 'renta',
                'monto': '1701.00',
                'metodo': 'efectivo',
                'referencia': '',
            },
        )

        self.assertEqual(PagoAlquiler.objects.count(), 0)
        self.assertEqual(self.presupuesto.saldo_pendiente, Decimal('1700.00'))

    def test_cliente_no_puede_registrar_pagos(self):
        self.client.force_login(self.cliente)

        respuesta = self.client.post(
            reverse('ventas:pago_registrar', args=[self.presupuesto.pk]),
            {'concepto': 'renta', 'monto': '100.00', 'metodo': 'efectivo'},
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(PagoAlquiler.objects.count(), 0)

    def test_mora_usa_porcentaje_diario_equivalente_y_aumenta_desde_el_dia_4(self):
        self.assertEqual(
            self.presupuesto.calcular_mora(1),
            Decimal('10.00'),
        )
        self.assertEqual(
            self.presupuesto.calcular_mora(3),
            Decimal('30.00'),
        )
        self.assertEqual(
            self.presupuesto.calcular_mora(4),
            Decimal('50.00'),
        )

    def test_admin_registra_reembolsos_parciales_sin_exceder_deposito_recibido(self):
        self.solicitud.fecha_salida = timezone.now() - timedelta(days=2)
        self.solicitud.entregado_por = self.admin
        self.solicitud.fecha_retorno = timezone.now()
        self.solicitud.recibido_por = self.admin
        self.solicitud.save(update_fields=[
            'fecha_salida',
            'entregado_por',
            'fecha_retorno',
            'recibido_por',
        ])
        PagoAlquiler.objects.create(
            presupuesto=self.presupuesto,
            concepto='deposito',
            monto=600,
            metodo='transferencia',
            registrado_por=self.admin,
        )
        self.client.force_login(self.admin)

        respuesta = self.client.post(
            reverse(
                'ventas:reembolso_registrar',
                args=[self.presupuesto.pk],
            ),
            {'monto': '400.00', 'metodo': 'transferencia', 'referencia': 'REF-1'},
        )

        self.assertRedirects(
            respuesta,
            reverse('ventas:presupuesto_detalle', args=[self.presupuesto.pk]),
        )
        self.assertEqual(self.presupuesto.deposito_reembolsado, Decimal('400.00'))
        self.assertEqual(
            self.presupuesto.deposito_por_reembolsar,
            Decimal('200.00'),
        )

        self.client.post(
            reverse(
                'ventas:reembolso_registrar',
                args=[self.presupuesto.pk],
            ),
            {'monto': '201.00', 'metodo': 'efectivo', 'referencia': ''},
        )
        self.assertEqual(self.presupuesto.reembolsos_deposito.count(), 1)
