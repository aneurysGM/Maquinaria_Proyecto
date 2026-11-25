from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from .models import SolicitudAlquiler


class DepositoGarantiaManualTests(TestCase):
    def setUp(self):
        self.cliente = UsuarioPersonalizado.objects.create_user(
            email='deposito@example.com',
            password='pass',
            rol=RolUsuario.CLIENTE,
        )
        categoria = Categoria.objects.create(nombre='Depósitos manuales')
        self.maquinaria = Maquinaria.objects.create(
            categoria=categoria,
            codigo='DEP-01',
            nombre='Máquina de prueba',
            costo_adquisicion=5070000,
            tarifa_diaria=1000,
            tarifa_semanal=6000,
            tarifa_mensual=20000,
            deposito_garantia=12345,
        )
        self.unidad = Unidad.objects.create(
            maquinaria=self.maquinaria,
            numero_serie='DEP-SERIE-01',
        )
        self.client.force_login(self.cliente)

    def test_deposito_no_cambia_al_modificar_costo_o_guardar_otro_campo(self):
        self.maquinaria.refresh_from_db()
        self.assertEqual(self.maquinaria.deposito_garantia, 12345)
        self.maquinaria.costo_adquisicion = 100000
        self.maquinaria.save()
        self.maquinaria.deposito_garantia = 99999
        self.maquinaria.nombre = 'Nombre actualizado'
        self.maquinaria.save(update_fields=['nombre'])
        self.maquinaria.refresh_from_db()
        self.assertEqual(self.maquinaria.deposito_garantia, 12345)

    def test_solicitud_conserva_deposito_manual_sin_importar_duracion(self):
        fecha_inicio = timezone.localdate() + timedelta(days=1)
        pagina = self.client.get(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
        )
        self.assertContains(pagina, 'data-deposito="12345"')
        for plan, cantidad in (('diario', 1), ('semanal', 2), ('mensual', 1)):
            with self.subTest(plan=plan):
                respuesta = self.client.post(
                    reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
                    {
                        'fecha_inicio': fecha_inicio.isoformat(),
                        'plan': plan,
                        'cantidad': cantidad,
                        'comentario': '',
                    },
                )
                solicitud = SolicitudAlquiler.objects.get(
                    unidad=self.unidad, plan=plan,
                )
                self.assertRedirects(
                    respuesta,
                    reverse('ventas:presupuesto_detalle', args=[solicitud.presupuesto.pk]),
                )
                self.assertEqual(solicitud.presupuesto.deposito_garantia, 12345)

        self.maquinaria.deposito_garantia = 0
        self.maquinaria.save()
        solicitud.presupuesto.refresh_from_db()
        self.assertEqual(solicitud.presupuesto.deposito_garantia, 12345)
        respuesta = self.client.post(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
            {
                'fecha_inicio': (fecha_inicio + timedelta(days=60)).isoformat(),
                'plan': 'mensual',
                'cantidad': 1,
            },
        )
        solicitud_cero = SolicitudAlquiler.objects.get(
            unidad=self.unidad, fecha_inicio=fecha_inicio + timedelta(days=60),
        )
        self.assertRedirects(
            respuesta,
            reverse('ventas:presupuesto_detalle', args=[solicitud_cero.presupuesto.pk]),
        )
        self.assertEqual(solicitud_cero.presupuesto.deposito_garantia, 0)
