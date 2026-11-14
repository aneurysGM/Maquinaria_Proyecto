from datetime import date, datetime, timedelta, timezone as tz
from decimal import Decimal
from unittest.mock import patch

from django.contrib.messages import ERROR, get_messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase
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
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')
        solicitud = SolicitudAlquiler.objects.get()
        self.assertEqual(solicitud.estado, 'Pendiente')
        self.assertContains(
            self.client.get(reverse('catalogo')),
            self.maquinaria.nombre,
        )
        self.assertContains(
            self.client.get(reverse('cuentas:dashboard')),
            self.maquinaria.nombre,
        )
        self.assertContains(
            self.client.get(reverse('alquileres:solicitud_lista')),
            reverse('inventario:maquinaria_detalle', args=[self.unidad.pk]),
        )
        self.assertEqual(solicitud.fecha_fin, timezone.localdate() + timedelta(days=13))
        self.assertEqual(solicitud.presupuesto.importe_renta, Decimal('9000.00'))
        self.assertEqual(solicitud.presupuesto.importe_total, Decimal('12000.00'))
        self.assertContains(self.client.get(reverse('alquileres:solicitud_detalle', args=[solicitud.pk])), 'Obra integración')
        self.client.force_login(self.admin)
        self.client.post(reverse('alquileres:solicitud_resolver', args=[solicitud.pk]), {'decision': 'Aprobada'})
        solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(
            solicitud.fecha_limite_pago,
            solicitud.fecha_revision + timedelta(days=5),
        )
        self.assertContains(
            self.client.get(reverse('alquileres:solicitud_lista')),
            'Fecha límite del pago inicial',
        )
        self.completar_pago_inicial(solicitud)
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Alquilado')
        self.assertNotContains(
            self.client.get(reverse('catalogo')),
            self.maquinaria.nombre,
        )
        self.assertNotContains(
            self.client.get(reverse('cuentas:dashboard')),
            self.maquinaria.nombre,
        )
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

    def test_devolucion_atrasada_tiene_filtro_admin_y_aviso_para_cliente(self):
        entrega = self.crear_entrega(atraso=2)

        self.client.force_login(self.admin)
        pendientes = self.client.get(reverse('alquileres:entrega_lista'))
        self.assertContains(pendientes, 'Hay 1 maquinaria con devolución atrasada.')
        self.assertContains(pendientes, 'Ver devoluciones atrasadas')
        self.assertEqual(pendientes.context['entregas_atrasadas_count'], 1)
        atrasadas = self.client.get(
            reverse('alquileres:entrega_lista'),
            {'estado': 'atrasadas'},
        )
        self.assertEqual(list(atrasadas.context['entregas']), [entrega])
        self.assertContains(atrasadas, 'Excavadora integración')
        self.assertContains(atrasadas, '2 día(s) de atraso')

        self.client.force_login(self.cliente)
        solicitudes = self.client.get(reverse('alquileres:solicitud_lista'))
        self.assertContains(
            solicitudes,
            'Tienes atrasada la devolución de <strong>Excavadora integración</strong>',
        )
        self.assertContains(solicitudes, 'La fecha estimada era el')

    def test_tres_planes_y_tarifas_contratadas_no_cambian(self):
        self.client.force_login(self.cliente)
        for indice, (plan, dias, tarifa) in enumerate(
            [('diario', 2, 750), ('semanal', 14, 4500), ('mensual', 60, 15000)]
        ):
            with self.subTest(plan=plan):
                if indice:
                    unidad = Unidad.objects.create(
                        maquinaria=self.maquinaria,
                        numero_serie=f'000045{indice}',
                        ubicacion_actual='Santo Domingo',
                        horas_uso=Decimal('10.5'),
                    )
                else:
                    unidad = self.unidad
                self.client.post(reverse('alquileres:solicitud_registrar', args=[unidad.pk]), {
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
        self.client.post(url, datos)
        self.assertEqual(SolicitudAlquiler.objects.count(), 1)
        self.assertEqual(PresupuestoAlquiler.objects.count(), 1)
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')

    def test_formulario_no_puede_liberar_unidad_con_solicitud_activa(self):
        self.crear_solicitud()
        self.unidad.estado = 'Alquilado'
        self.unidad.save(update_fields=['estado'])
        datos = {
            'categoria': self.maquinaria.categoria_id,
            'codigo': self.maquinaria.codigo,
            'nombre': self.maquinaria.nombre,
            'descripcion': self.maquinaria.descripcion,
            'marca': self.maquinaria.marca or '',
            'modelo': self.maquinaria.modelo or '',
            'costo_adquisicion': self.maquinaria.costo_adquisicion,
            'tarifa_diaria': self.maquinaria.tarifa_diaria,
            'tarifa_semanal': self.maquinaria.tarifa_semanal,
            'tarifa_mensual': self.maquinaria.tarifa_mensual,
            'deposito_garantia': self.maquinaria.deposito_garantia,
            'numero_serie': self.unidad.numero_serie,
            'estado': 'Disponible',
            'horas_uso': self.unidad.horas_uso,
            'fecha_adquisicion': '',
            'anio_fabricacion': '',
            'ubicacion_actual': self.unidad.ubicacion_actual,
        }

        form = MaquinariaIntegralForm(data=datos, unidad=self.unidad)

        self.assertFalse(form.is_valid())
        self.assertIn('estado', form.errors)

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

    def test_unidades_no_disponibles_no_admiten_nuevas_solicitudes(self):
        url = reverse('alquileres:solicitud_registrar', args=[self.unidad.pk])
        datos = {
            'fecha_inicio': timezone.localdate().isoformat(),
            'plan': 'diario',
            'cantidad': 1,
        }
        for usuario in (self.cliente, self.admin):
            self.client.force_login(usuario)
            for estado in ('Mantenimiento', 'Baja'):
                with self.subTest(usuario=usuario.rol, estado=estado):
                    Unidad.objects.filter(pk=self.unidad.pk).update(estado=estado)
                    respuesta = self.client.post(url, datos)
                    self.assertEqual(respuesta.status_code, 302)
                    self.assertFalse(SolicitudAlquiler.objects.exists())
        Unidad.objects.filter(pk=self.unidad.pk).update(estado='Disponible')

    def test_rechazar_solicitud_pendiente_deja_unidad_disponible(self):
        self.client.force_login(self.cliente)
        self.client.post(reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]), {
            'fecha_inicio': timezone.localdate().isoformat(),
            'plan': 'diario',
            'cantidad': 1,
        })
        solicitud = SolicitudAlquiler.objects.get()
        self.unidad.refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')

        self.client.force_login(self.admin)
        self.client.post(
            reverse('alquileres:solicitud_resolver', args=[solicitud.pk]),
            {'decision': 'Rechazada', 'motivo_rechazo': 'No disponible para la obra'},
        )

        solicitud.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertEqual(solicitud.estado, 'Rechazada')
        self.assertEqual(self.unidad.estado, 'Disponible')

    def test_solicitudes_pendientes_siguen_independientes_al_aprobar_una(self):
        datos = {
            'fecha_inicio': timezone.localdate().isoformat(),
            'plan': 'diario',
            'cantidad': 1,
        }
        solicitudes = {}
        for cliente in (self.cliente, self.otro):
            self.client.force_login(cliente)
            respuesta = self.client.post(
                reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
                datos,
            )
            self.assertEqual(respuesta.status_code, 302)
            solicitudes[cliente.pk] = SolicitudAlquiler.objects.get(cliente=cliente)
            self.unidad.refresh_from_db()
            self.assertEqual(self.unidad.estado, 'Disponible')

        self.client.force_login(self.cliente)
        solicitudes_cliente = self.client.get(
            reverse('alquileres:solicitud_lista'),
        )
        self.assertEqual(
            list(solicitudes_cliente.context['solicitudes']),
            [solicitudes[self.cliente.pk]],
        )
        self.assertContains(
            self.client.get(reverse('catalogo')),
            self.maquinaria.nombre,
        )

        self.client.force_login(self.admin)
        solicitudes_admin = self.client.get(
            reverse('alquileres:solicitud_lista'),
        )
        self.assertEqual(len(solicitudes_admin.context['solicitudes']), 2)
        self.client.post(
            reverse(
                'alquileres:solicitud_resolver',
                args=[solicitudes[self.cliente.pk].pk],
            ),
            {'decision': 'Aprobada'},
        )

        self.unidad.refresh_from_db()
        solicitudes[self.cliente.pk].refresh_from_db()
        solicitudes[self.otro.pk].refresh_from_db()
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(solicitudes[self.cliente.pk].estado, 'Aprobada')
        self.assertEqual(solicitudes[self.otro.pk].estado, 'Pendiente')
        self.client.force_login(self.cliente)
        solicitudes_cliente_aprobado = self.client.get(
            reverse('alquileres:solicitud_lista'),
        )
        self.assertEqual(
            list(solicitudes_cliente_aprobado.context['solicitudes']),
            [solicitudes[self.cliente.pk]],
        )
        self.assertContains(solicitudes_cliente_aprobado, 'Pendiente de pago')
        self.assertContains(
            self.client.get(reverse('inventario:maquinaria_lista')),
            self.maquinaria.nombre,
        )
        self.client.force_login(self.otro)
        solicitudes_otro = self.client.get(
            reverse('alquileres:solicitud_lista'),
        )
        self.assertEqual(
            list(solicitudes_otro.context['solicitudes']),
            [solicitudes[self.otro.pk]],
        )
        self.assertContains(solicitudes_otro, 'Pendiente de aprobación')
        self.assertContains(
            self.client.get(reverse('catalogo')),
            self.maquinaria.nombre,
        )

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
        self.completar_pago_inicial(aprobada)
        pendiente = self.crear_solicitud(fecha_inicio=aprobada.fecha_fin, fecha_fin=aprobada.fecha_fin)
        self.client.force_login(self.admin)
        url = reverse('alquileres:solicitud_resolver', args=[pendiente.pk])
        self.client.post(url, {'decision': 'Aprobada'})
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, 'Pendiente')
        self.client.post(url, {'decision': 'Rechazada', 'motivo_rechazo': 'Período ocupado'})
        self.client.post(url, {'decision': 'Aprobada'})
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, 'Rechazada')

    def test_solicitud_y_aprobacion_no_se_bloquean_por_alquiler_aprobado_devuelto(self):
        hoy = timezone.localdate()
        anterior = self.crear_solicitud(
            estado='Aprobada',
            fecha_inicio=hoy,
            fecha_fin=hoy + timedelta(days=7),
            fecha_salida=timezone.now() - timedelta(days=2),
            entregado_por=self.admin,
            fecha_retorno=timezone.now() - timedelta(days=1),
            recibido_por=self.admin,
        )
        self.unidad.estado = 'Disponible'
        self.unidad.save(update_fields=['estado'])
        self.client.force_login(self.cliente)

        respuesta = self.client.post(
            reverse('alquileres:solicitud_registrar', args=[self.unidad.pk]),
            {
                'fecha_inicio': hoy.isoformat(),
                'plan': 'semanal',
                'cantidad': 1,
            },
        )

        nueva = SolicitudAlquiler.objects.exclude(pk=anterior.pk).get()
        self.assertEqual(nueva.estado, 'Pendiente')
        self.assertRedirects(
            respuesta,
            reverse('ventas:presupuesto_detalle', args=[nueva.presupuesto.pk]),
        )
        self.client.force_login(self.admin)
        self.client.post(
            reverse('alquileres:solicitud_resolver', args=[nueva.pk]),
            {'decision': 'Aprobada'},
        )
        nueva.refresh_from_db()
        self.assertEqual(nueva.estado, 'Aprobada')

    def test_roles_csrf_get_y_campos_extra_no_autorizan_movimientos(self):
        solicitud = self.crear_solicitud(estado='Aprobada')
        self.completar_pago_inicial(solicitud)
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
        self.completar_pago_inicial(futura)
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
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '11'})
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.is_active)
        avisos = [str(aviso) for aviso in get_messages(respuesta.wsgi_request)]
        self.assertTrue(any('primera devolución con más de 3 días' in aviso for aviso in avisos), avisos)

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

    def datos_edicion_horometro(self, horas, estado='Disponible'):
        return dict(
            categoria=self.maquinaria.categoria_id, codigo=self.maquinaria.codigo,
            nombre='Nombre editado', descripcion=self.maquinaria.descripcion,
            costo_adquisicion='90000', tarifa_diaria='750', tarifa_semanal='4500',
            tarifa_mensual='15000', deposito_garantia='3000', numero_serie=self.unidad.numero_serie,
            estado=estado, horas_uso=str(horas), ubicacion_actual='Santo Domingo',
        )

    def test_formulario_abierto_antes_del_retorno_no_rebaja_horometro(self):
        entrega = self.crear_entrega()
        self.unidad.refresh_from_db()
        form = MaquinariaIntegralForm(self.datos_edicion_horometro('10.5', 'Alquilado'), unidad=self.unidad)
        self.assertTrue(form.is_valid(), form.errors)
        self.client.force_login(self.admin)
        self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '17.5'})
        with self.assertRaises(ValidationError) as error:
            form.save()
        self.assertIn('horas_uso', error.exception.message_dict)
        self.unidad.refresh_from_db()
        self.maquinaria.refresh_from_db()
        self.assertEqual(self.unidad.horas_uso, Decimal('17.5'))
        self.assertEqual(self.unidad.estado, 'Disponible')
        self.assertEqual(self.maquinaria.nombre, 'Excavadora integración')

    def test_edicion_admite_lectura_actual_o_superior(self):
        for horas in ('10.5', '17.5'):
            with self.subTest(horas=horas):
                form = MaquinariaIntegralForm(self.datos_edicion_horometro(horas), unidad=self.unidad)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                self.unidad.refresh_from_db()
                self.assertEqual(self.unidad.horas_uso, Decimal(horas))

    def test_reactivacion_no_rebaja_horometro_y_revierte_catalogo(self):
        self.maquinaria.activo = False
        self.maquinaria.save(update_fields=['activo'])
        Unidad.objects.filter(pk=self.unidad.pk).update(activo=False, horas_uso=Decimal('17.5'))
        form = MaquinariaIntegralForm(self.datos_edicion_horometro('10.5'))
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValidationError):
            form.save()
        self.unidad.refresh_from_db()
        self.maquinaria.refresh_from_db()
        self.assertEqual(self.unidad.horas_uso, Decimal('17.5'))
        self.assertFalse(self.unidad.activo)
        self.assertFalse(self.maquinaria.activo)
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


class MensajesRetornoTests(DatosIntegracion, TransactionTestCase):
    def setUp(self):
        self.crear_datos()
        self.client.force_login(self.admin)

    def test_mora_se_muestra_despues_de_confirmar_y_sobrevive_redireccion(self):
        entrega = self.crear_entrega(atraso=4)
        with patch.object(connection, '_commit', wraps=connection._commit) as confirmar:
            respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '18'}, follow=True)
        self.assertTrue(confirmar.called)
        entrega.refresh_from_db()
        self.assertIsNotNone(entrega.fecha_retorno)
        avisos = [str(aviso) for aviso in get_messages(respuesta.wsgi_request)]
        self.assertTrue(any('Mora calculada: $375.00' in aviso for aviso in avisos), avisos)
        self.assertTrue(any('primera devolución con más de 3 días' in aviso for aviso in avisos), avisos)

    def test_fallo_al_confirmar_transaccion_solo_muestra_error(self):
        entrega = self.crear_entrega(atraso=4)
        with patch.object(connection, '_commit', side_effect=DatabaseError('fallo al confirmar')):
            respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '18'})
        avisos = list(get_messages(respuesta.wsgi_request))
        self.assertEqual(len(avisos), 1, [str(aviso) for aviso in avisos])
        self.assertEqual(avisos[0].level, ERROR)
        self.assertIn('No se guardaron cambios', str(avisos[0]))
        entrega.refresh_from_db()
        self.unidad.refresh_from_db()
        self.assertIsNone(entrega.fecha_retorno)
        self.assertEqual(self.unidad.estado, 'Alquilado')
        self.assertEqual(self.unidad.horas_uso, Decimal('10.5'))
        self.assertEqual(entrega.presupuesto.mora_total, 0)

    def test_fallo_en_suspension_no_muestra_mora_y_revierte_retorno(self):
        anterior = self.crear_entrega(atraso=5)
        anterior.fecha_retorno = timezone.now() - timedelta(days=1)
        anterior.recibido_por = self.admin
        anterior.dias_atraso = 4
        anterior.save()
        entrega = self.crear_entrega(atraso=4)
        with patch('apps.cuentas.models.UsuarioPersonalizado.save', side_effect=DatabaseError('fallo al suspender')):
            respuesta = self.client.post(reverse('alquileres:solicitud_retorno', args=[entrega.pk]), {'horas_uso_actualizadas': '18'})
        avisos = list(get_messages(respuesta.wsgi_request))
        self.assertEqual(len(avisos), 1, [str(aviso) for aviso in avisos])
        self.assertEqual(avisos[0].level, ERROR)
        entrega.refresh_from_db()
        self.unidad.refresh_from_db()
        self.cliente.refresh_from_db()
        self.assertIsNone(entrega.fecha_retorno)
        self.assertEqual(self.unidad.horas_uso, Decimal('10.5'))
        self.assertEqual(self.unidad.estado, 'Alquilado')
        self.assertEqual(entrega.presupuesto.mora_total, 0)
        self.assertTrue(self.cliente.is_active)
        self.assertIsNone(self.cliente.suspension_hasta)
