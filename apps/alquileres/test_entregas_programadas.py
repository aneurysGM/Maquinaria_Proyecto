from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PagoAlquiler, PresupuestoAlquiler
from .models import SolicitudAlquiler


class SalidasProgramadasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-salidas@example.com',
            rol=RolUsuario.ADMINISTRADOR,
        )
        cls.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-salidas@example.com',
            rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Salidas programadas')
        maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='SAL-01',
            nombre='Excavadora programada',
            costo_adquisicion=Decimal('1000.00'),
            tarifa_diaria=Decimal('100.00'),
            tarifa_semanal=Decimal('500.00'),
            tarifa_mensual=Decimal('1500.00'),
            deposito_garantia=Decimal('100.00'),
        )
        cls.unidad = Unidad.objects.create(
            maquinaria=maquinaria,
            numero_serie='SAL-SERIE-01',
        )

    def setUp(self):
        self.client.force_login(self.admin)
        self.hoy = timezone.localdate()

    def crear_solicitud(self, *, inicio=None, fin=None, pagada=True):
        solicitud = SolicitudAlquiler.objects.create(
            cliente=self.cliente,
            unidad=self.unidad,
            estado='Aprobada',
            fecha_inicio=inicio or self.hoy,
            fecha_fin=fin or self.hoy + timedelta(days=2),
            fecha_revision=timezone.now(),
            revisado_por=self.admin,
        )
        presupuesto = PresupuestoAlquiler.objects.create(
            solicitud=solicitud,
            tarifa_periodo=Decimal('100.00'),
            importe_renta=Decimal('100.00'),
            deposito_garantia=Decimal('100.00'),
        )
        if pagada:
            PagoAlquiler.objects.create(
                presupuesto=presupuesto,
                concepto='renta',
                monto=Decimal('100.00'),
                metodo='efectivo',
                registrado_por=self.admin,
            )
            PagoAlquiler.objects.create(
                presupuesto=presupuesto,
                concepto='deposito',
                monto=Decimal('100.00'),
                metodo='efectivo',
                registrado_por=self.admin,
            )
        return solicitud

    def test_muestra_solo_salidas_pagadas_cuyo_periodo_incluye_hoy(self):
        vigente = self.crear_solicitud()
        self.crear_solicitud(pagada=False)
        self.crear_solicitud(
            inicio=self.hoy + timedelta(days=1),
            fin=self.hoy + timedelta(days=2),
        )
        self.crear_solicitud(
            inicio=self.hoy - timedelta(days=2),
            fin=self.hoy - timedelta(days=1),
        )

        respuesta = self.client.get(reverse('alquileres:entrega_lista'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertQuerySetEqual(
            respuesta.context['entregas'],
            [vigente],
        )
        self.assertContains(respuesta, 'Renta y depósito pagados')

    def test_pago_parcial_no_aparece_en_salidas_programadas(self):
        solicitud = self.crear_solicitud(pagada=False)
        PagoAlquiler.objects.create(
            presupuesto=solicitud.presupuesto,
            concepto='renta',
            monto=Decimal('100.00'),
            metodo='efectivo',
            registrado_por=self.admin,
        )

        respuesta = self.client.get(
            reverse('alquileres:entrega_lista'),
            {'estado': 'programadas'},
        )

        self.assertNotContains(respuesta, f'Solicitud #{solicitud.pk}')
