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


class SalidaMaquinariaForm(forms.Form):
    """Formulario administrativo para registrar la salida física del equipo a la obra."""
    observaciones_salida = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Condiciones de entrega, accesorios incluidos, etc.'}),
        label='Observaciones de salida'
    )


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
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Estado en el que regresa la máquina, daños o observaciones.'}),
        label='Observaciones de retorno'
    )