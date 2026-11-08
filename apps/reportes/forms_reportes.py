from django import forms
from django.contrib.auth import get_user_model

from apps.alquileres.models import SolicitudAlquiler
from apps.inventario.models import Unidad
from apps.mantenimiento.models import Mantenimiento


class RangoFechasReporteForm(forms.Form):
    desde = forms.DateField(
        required=False,
        label='Desde',
        input_formats=('%Y-%m-%d',),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    hasta = forms.DateField(
        required=False,
        label='Hasta',
        input_formats=('%Y-%m-%d',),
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        desde = cleaned_data.get('desde')
        hasta = cleaned_data.get('hasta')
        if desde and hasta and desde > hasta:
            raise forms.ValidationError(
                'La fecha inicial no puede ser posterior a la fecha final.'
            )
        return cleaned_data


class MaquinariaReporteForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Código, nombre, serie o ubicación',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Escribe un término para buscar',
        }),
    )
    estado = forms.ChoiceField(
        required=False,
        label='Estado',
        choices=(('', 'Todos los estados'),) + Unidad.ESTADOS,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class SolicitudesReporteForm(RangoFechasReporteForm):
    estado = forms.ChoiceField(
        required=False,
        label='Estado',
        choices=(('', 'Todos los estados'),) + tuple(SolicitudAlquiler.ESTADOS),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    cliente = forms.ModelChoiceField(
        required=False,
        label='Cliente',
        queryset=get_user_model().objects.none(),
        empty_label='Todos los clientes',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cliente'].queryset = get_user_model().objects.filter(
            solicitudes_alquiler__isnull=False,
        ).distinct().order_by('email')


class EntregasReporteForm(RangoFechasReporteForm):
    situacion = forms.ChoiceField(
        required=False,
        label='Situación de entrega',
        choices=(
            ('', 'Todas'),
            ('pendiente', 'Pendiente de devolución'),
            ('devuelta', 'Devuelta'),
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class UnidadReporteChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, unidad):
        return (
            f'{unidad.codigo} · {unidad.nombre} · '
            f'Serie: {unidad.numero_serie} · #{unidad.pk}'
        )


class MantenimientosReporteForm(RangoFechasReporteForm):
    unidad = UnidadReporteChoiceField(
        required=False,
        label='Unidad',
        queryset=Unidad.objects.none(),
        empty_label='Todas las unidades',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    tipo = forms.ChoiceField(
        required=False,
        label='Tipo de mantenimiento',
        choices=(('', 'Todos los tipos'),) + tuple(Mantenimiento.TIPOS),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unidad'].queryset = Unidad.objects.select_related(
            'maquinaria'
        ).order_by('maquinaria__codigo', 'numero_serie')
