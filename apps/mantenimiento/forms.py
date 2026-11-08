from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from apps.inventario.models import Unidad
from apps.cuentas.models import permisos_panel
from .models import Mantenimiento


class UnidadMantenimientoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, unidad):
        return (
            f'Código: {unidad.maquinaria.codigo} · {unidad.maquinaria.nombre} '
            f'· Serie: {unidad.numero_serie} · Estado: {unidad.estado}'
        )


class MantenimientoForm(forms.Form):
    unidad = UnidadMantenimientoChoiceField(
        label='Maquinaria / unidad física', 
        queryset=Unidad.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Selecciona la serie de la unidad disponible o en mantenimiento.',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo permitimos programar mantenimiento a unidades activas que estén libres o ya en taller
        self.fields['unidad'].queryset = Unidad.objects.select_related('maquinaria').filter(
            activo=True, maquinaria__activo=True, estado__in=('Disponible', 'Mantenimiento'),
        )

    @transaction.atomic
    def save(self, *, tecnico):
        # Validar permisos de técnico o administrador
        permisos = permisos_panel(tecnico)
        if not (permisos.get('es_administrador') or permisos.get('es_tecnico')):
            raise PermissionDenied("No tienes permisos para registrar mantenimientos.")

        datos = self.cleaned_data
        
        # Bloqueo atómico para evitar condiciones de carrera
        unidad = Unidad.objects.select_for_update().select_related('maquinaria').filter(pk=datos['unidad'].pk).first()
        if unidad is None or not unidad.activo or not unidad.maquinaria.activo or unidad.estado not in ('Disponible', 'Mantenimiento'):
            raise ValidationError('La unidad ya no está disponible para registrar mantenimiento. Selecciona otra unidad.')
        
        mantenimiento = Mantenimiento(
            unidad=unidad, 
            tecnico=tecnico,
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