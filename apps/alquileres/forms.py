from django import forms
from django.utils import timezone
from .models import SolicitudAlquiler

class SolicitudAlquilerForm(forms.ModelForm):
    class Meta:
        model = SolicitudAlquiler
        fields = ['fecha_inicio', 'plan', 'cantidad', 'comentario']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'step': '1'
            }),
            'comentario': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3, 
                'placeholder': 'Indica detalles de la obra, ubicación exacta o requerimientos especiales...'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        cantidad = cleaned_data.get('cantidad')
        hoy = timezone.localdate()

        if fecha_inicio and fecha_inicio < hoy:
            raise forms.ValidationError('La fecha de inicio no puede ser en el pasado.')

        if cantidad is not None and cantidad < 1:
            self.add_error('cantidad', 'La cantidad debe ser al menos 1.')

        return cleaned_data


class SolicitudFiltroForm(forms.Form):
    codigo_exacto = forms.CharField(required=False, max_length=20, widget=forms.HiddenInput())
    q = forms.CharField(
        label='Buscar', required=False, max_length=200,
        widget=forms.TextInput(attrs={
            'type': 'search', 'class': 'form-control',
            'placeholder': 'Cliente, maquinaria, serie o solicitud #',
        }),
    )
    estado = forms.ChoiceField(
        label='Estado', required=False,
        choices=[('', 'Todos los estados'), *SolicitudAlquiler.ESTADOS],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    desde = forms.DateField(
        label='Desde', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
    )
    hasta = forms.DateField(
        label='Hasta', required=False, input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        datos = super().clean()
        if datos.get('codigo_exacto', '').casefold() != datos.get('q', '').casefold():
            datos['codigo_exacto'] = ''
        desde, hasta = datos.get('desde'), datos.get('hasta')
        if desde and hasta and hasta < desde:
            self.add_error('hasta', 'La fecha Hasta debe ser igual o posterior a Desde.')
        return datos


class RetornoMaquinariaForm(forms.Form):
    """Formulario administrativo para registrar el retorno de la máquina y actualizar horas."""
    horas_uso_actualizadas = forms.DecimalField(
        max_digits=10, 
        decimal_places=1,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        label='Horas de uso totales del horómetro'
    )
    observaciones_retorno = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Estado en el que regresa la máquina, daños o observaciones.'}),
        label='Observaciones de retorno'
    )
