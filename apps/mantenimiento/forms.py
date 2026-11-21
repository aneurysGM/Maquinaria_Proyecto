from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from functools import partial
from apps.alquileres.bloqueos import bloquear_unidad
from apps.alquileres.models import SolicitudAlquiler
from apps.alquileres.notificaciones import notificar_cancelacion_mantenimiento
from apps.inventario.models import Unidad
from apps.cuentas.models import RolUsuario, UsuarioPersonalizado, permisos_panel
from apps.tecnico_mantenimiento.especialidades import opciones_especialidad
from .models import Mantenimiento


class UnidadMantenimientoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, unidad):
        return (
            f'Código: {unidad.maquinaria.codigo} · {unidad.maquinaria.nombre} '
            f'· Serie: {unidad.numero_serie} · Estado: {unidad.estado}'
        )


class TecnicoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, tecnico):
        return f'{tecnico.get_full_name() or tecnico.email} · {tecnico.especialidad or "Sin especialidad"}'


class MantenimientoForm(forms.Form):
    especialidad = forms.ChoiceField(
        label='Filtrar por especialidad', required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    tecnico_responsable = TecnicoChoiceField(
        label='Técnico responsable', queryset=UsuarioPersonalizado.objects.none(),
        empty_label='Selecciona un técnico',
        widget=forms.Select(attrs={'class': 'form-select'}),
        error_messages={'invalid_choice': 'Selecciona un técnico activo y disponible de la especialidad indicada.'},
    )
    unidad = UnidadMantenimientoChoiceField(
        label='Maquinaria / unidad física', 
        queryset=Unidad.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Una unidad reservada requiere confirmar el mantenimiento forzado.',
    )
    fecha = forms.DateField(
        label='Fecha de ejecución', 
        input_formats=('%Y-%m-%d',),
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
    )
    tipo = forms.ChoiceField(
        label='Tipo de mantenimiento', 
        choices=Mantenimiento.TIPOS,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    descripcion = forms.CharField(
        label='Descripción del trabajo', 
        max_length=300, 
        strip=True, 
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalla las piezas cambiadas, reparaciones o revisiones...'}),
    )
    costo = forms.DecimalField(
        label='Costo de la intervención', 
        max_digits=18, 
        decimal_places=2, 
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    forzar = forms.BooleanField(
        required=False,
        label='Forzar mantenimiento y cancelar reservas sin entregar',
        help_text='Cancela las reservas aprobadas vigentes o futuras sin entregar, notifica a los clientes y deja sus pagos pendientes de reembolso.',
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.tecnicos_disponibles = UsuarioPersonalizado.objects.filter(
            rol=RolUsuario.TECNICO, is_active=True, disponible=True,
        ).order_by('first_name', 'last_name', 'email')
        if usuario.es_administrador:
            self.fields['especialidad'].choices = [('', 'Todas las especialidades'), *opciones_especialidad()]
            especialidad = self.data.get('especialidad', '') if self.is_bound else self.initial.get('especialidad', '')
            tecnicos = self.tecnicos_disponibles
            if especialidad:
                tecnicos = tecnicos.filter(especialidad=especialidad)
            self.fields['tecnico_responsable'].queryset = tecnicos
            self.sin_tecnicos = not tecnicos.exists()
        else:
            # El responsable se obtiene exclusivamente de la sesión del técnico.
            self.fields.pop('especialidad')
            self.fields.pop('tecnico_responsable')
        # Solo permitimos programar mantenimiento a unidades activas que estén libres o ya en taller
        self.fields['unidad'].queryset = Unidad.objects.select_related('maquinaria').filter(
            activo=True, maquinaria__activo=True, estado__in=('Disponible', 'Mantenimiento', 'Alquilado'),
        )

    @transaction.atomic
    def save(self, *, request=None):
        # Validar permisos de técnico o administrador
        usuario = UsuarioPersonalizado.objects.select_for_update().get(pk=self.usuario.pk)
        permisos = permisos_panel(usuario)
        if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
            raise PermissionDenied("No tienes permisos para registrar mantenimientos.")

        datos = self.cleaned_data
        if usuario.es_administrador:
            tecnico = UsuarioPersonalizado.objects.select_for_update().filter(
                pk=datos['tecnico_responsable'].pk,
                rol=RolUsuario.TECNICO, is_active=True, disponible=True,
            ).first()
            especialidad = datos.get('especialidad')
            if tecnico is None or (especialidad and tecnico.especialidad != especialidad):
                raise ValidationError('El técnico ya no está activo y disponible para esa especialidad. Selecciona otro.')
        else:
            tecnico = usuario
        
        # Bloqueo atómico para evitar condiciones de carrera
        try:
            unidad = bloquear_unidad(pk=datos['unidad'].pk)
        except Unidad.DoesNotExist:
            raise ValidationError('La unidad ya no existe.')
        if not unidad.activo or not unidad.maquinaria.activo or unidad.estado not in ('Disponible', 'Mantenimiento', 'Alquilado'):
            raise ValidationError('La unidad ya no está disponible para registrar mantenimiento. Selecciona otra unidad.')
        if SolicitudAlquiler.objects.filter(
            unidad=unidad, fecha_salida__isnull=False, fecha_retorno__isnull=True,
        ).exists():
            raise ValidationError('La unidad está entregada a un cliente y debe retornar antes del mantenimiento.')

        reservas = list(SolicitudAlquiler.objects.select_for_update().select_related(
            'cliente', 'unidad__maquinaria',
        ).filter(
            unidad=unidad, estado='Aprobada', fecha_salida__isnull=True,
            fecha_retorno__isnull=True, fecha_fin__gte=timezone.localdate(),
        ).order_by('pk'))
        if (reservas or unidad.estado == 'Alquilado') and not datos['forzar']:
            raise ValidationError('Confirma el mantenimiento forzado para cancelar las reservas sin entregar.')

        ahora = timezone.now()
        for solicitud in reservas:
            solicitud.estado = 'Cancelada'
            solicitud.cancelada_por_mantenimiento = True
            solicitud.motivo_disponibilidad = 'La unidad requiere mantenimiento forzado.'
            solicitud.fecha_aviso_disponibilidad = None
            solicitud.aplazada = False
            solicitud.save(update_fields=[
                'estado', 'cancelada_por_mantenimiento', 'motivo_disponibilidad',
                'fecha_aviso_disponibilidad', 'aplazada',
            ])
            transaction.on_commit(partial(notificar_cancelacion_mantenimiento, solicitud, request=request))
        
        mantenimiento = Mantenimiento(
            unidad=unidad, 
            tecnico=tecnico,
            registrado_por=usuario,
            fecha=datos['fecha'],
            tipo=datos['tipo'],
            descripcion=datos['descripcion'],
            costo=datos['costo']
        )
        mantenimiento.full_clean()
        mantenimiento.save()
        
        # Automáticamente la unidad pasa al estado de Mantenimiento
        unidad.estado = 'Mantenimiento'
        unidad.save(update_fields=['estado'])
        
        return mantenimiento
