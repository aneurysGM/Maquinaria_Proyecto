"""Datos compartidos por las pruebas de integración, sin usuarios reales."""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from apps.inventario.models import Categoria, Maquinaria, Unidad
from apps.ventas.models import PresupuestoAlquiler
from .models import SolicitudAlquiler


class DatosIntegracion:
    @classmethod
    def crear_datos(cls):
        cls.admin = UsuarioPersonalizado.objects.create_user(
            email='admin-integracion@example.com', rol=RolUsuario.ADMINISTRADOR,
        )
        cls.cliente = UsuarioPersonalizado.objects.create_user(
            email='cliente-integracion@example.com', rol=RolUsuario.CLIENTE,
            first_name='Ana', last_name='Pérez',
        )
        cls.otro = UsuarioPersonalizado.objects.create_user(
            email='otro-integracion@example.com', rol=RolUsuario.CLIENTE,
        )
        cls.tecnico = UsuarioPersonalizado.objects.create_user(
            email='tecnico-integracion@example.com', rol=RolUsuario.TECNICO,
        )
        cls.superadmin = UsuarioPersonalizado.objects.create_superuser(
            email='super-integracion@example.com',
        )
        categoria = Categoria.objects.create(nombre='Categoría integración')
        cls.maquinaria = Maquinaria.objects.create(
            categoria=categoria, codigo='000123', nombre='Excavadora integración',
            descripcion='Equipo de pruebas', costo_adquisicion=90000,
            tarifa_diaria=Decimal('750.00'), tarifa_semanal=Decimal('4500.00'),
            tarifa_mensual=Decimal('15000.00'), deposito_garantia=Decimal('3000.00'),
        )
        cls.unidad = Unidad.objects.create(
            maquinaria=cls.maquinaria, numero_serie='0000456',
            ubicacion_actual='Santo Domingo', horas_uso=Decimal('10.5'),
        )

    def crear_solicitud(self, *, presupuesto=True, **campos):
        datos = dict(
            cliente=self.cliente, unidad=self.unidad,
            fecha_inicio=timezone.localdate(), fecha_fin=timezone.localdate(),
        )
        datos.update(campos)
        solicitud = SolicitudAlquiler.objects.create(**datos)
        if presupuesto:
            tarifa = getattr(solicitud.unidad.maquinaria, {
                'diario': 'tarifa_diaria', 'semanal': 'tarifa_semanal', 'mensual': 'tarifa_mensual',
            }[solicitud.plan])
            PresupuestoAlquiler.objects.create(
                solicitud=solicitud, tarifa_periodo=tarifa,
                importe_renta=tarifa * solicitud.cantidad,
                deposito_garantia=solicitud.unidad.maquinaria.deposito_garantia,
            )
        return solicitud

    def crear_entrega(self, *, atraso=0, **campos):
        ahora = timezone.now()
        datos = dict(
            estado='Aprobada', fecha_inicio=timezone.localdate() - timedelta(days=10),
            fecha_fin=timezone.localdate() - timedelta(days=atraso),
            fecha_salida=ahora - timedelta(days=10), entregado_por=self.admin,
        )
        datos.update(campos)
        solicitud = self.crear_solicitud(**datos)
        Unidad.objects.filter(pk=solicitud.unidad_id).update(estado='Alquilado')
        return solicitud
