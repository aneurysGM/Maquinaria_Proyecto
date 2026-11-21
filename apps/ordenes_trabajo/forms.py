from django import forms
from django.forms import BaseFormSet, formset_factory

from .models import PuntoChecklist, Repuesto


class ActualizarOrdenForm(forms.Form):
    estado = forms.ChoiceField(
        label='Nuevo estado',
        choices=(
            ('diagnostico', 'En diagnóstico'),
            ('reparacion', 'En reparación'),
            ('esperando_repuestos', 'Esperando repuestos'),
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    dias_estimados = forms.IntegerField(
        label='Días estimados restantes',
        required=False,
        min_value=1,
        max_value=36500,
        help_text='Obligatorio en reparación; opcional durante el diagnóstico.',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '36500'}),
    )
    horas_trabajo = forms.DecimalField(
        label='Horas de mano de obra en esta actualización',
        max_digits=8,
        decimal_places=1,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'step': '0.1',
        }),
    )
    horometro = forms.DecimalField(
        label='Lectura actual del horómetro',
        max_digits=10,
        decimal_places=1,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0',
            'step': '0.1',
        }),
    )
    observaciones = forms.CharField(
        label='Observaciones técnicas',
        max_length=2000,
        strip=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Describe qué encontraste, el trabajo realizado y cómo quedó el equipo.',
        }),
    )

    def clean(self):
        datos = super().clean()
        if datos.get('estado') == 'reparacion' and datos.get('dias_estimados') is None:
            self.add_error('dias_estimados', 'Indica los días estimados para la reparación.')
        return datos


class ChecklistForm(forms.Form):
    def __init__(self, *args, checklist_existente=None, **kwargs):
        super().__init__(*args, **kwargs)
        checklist_existente = checklist_existente or {}
        self.puntos = PuntoChecklist.PUNTOS
        opciones = [('', 'Selecciona un resultado'), *PuntoChecklist.RESULTADOS]
        for codigo, etiqueta in self.puntos:
            actual = checklist_existente.get(codigo, {})
            self.fields[f'resultado_{codigo}'] = forms.ChoiceField(
                label=etiqueta,
                choices=opciones,
                widget=forms.Select(attrs={'class': 'form-select'}),
                initial=actual.get('resultado', ''),
            )
            self.fields[f'observacion_{codigo}'] = forms.CharField(
                label='Observación (opcional)',
                max_length=500,
                required=False,
                widget=forms.TextInput(attrs={
                    'class': 'form-control',
                    'placeholder': 'Anota hallazgos o déjalo vacío si está correcto.',
                }),
                initial=actual.get('observacion', ''),
            )

    def resultados(self):
        return {
            codigo: {
                'resultado': self.cleaned_data[f'resultado_{codigo}'],
                'observacion': self.cleaned_data[f'observacion_{codigo}'],
            }
            for codigo, _etiqueta in self.puntos
        }


class DetalleSolicitudRepuestoForm(forms.Form):
    codigo = forms.CharField(
        label='Código',
        max_length=40,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    nombre = forms.CharField(
        label='Nombre de la pieza o material',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    unidad_medida = forms.CharField(
        label='Unidad',
        max_length=20,
        initial='pieza',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'pieza, litro, metro...',
        }),
    )
    cantidad = forms.DecimalField(
        label='Cantidad solicitada',
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'step': '0.01',
        }),
    )


class BaseDetalleSolicitudRepuestoFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(form.cleaned_data for form in self.forms):
            raise forms.ValidationError('Agrega al menos un repuesto o material.')


SolicitudRepuestoFormSet = formset_factory(
    DetalleSolicitudRepuestoForm,
    formset=BaseDetalleSolicitudRepuestoFormSet,
    extra=1,
    max_num=10,
    validate_max=True,
)


class ComentarioOrdenForm(forms.Form):
    comentario = forms.CharField(
        label='Comentario técnico',
        max_length=2000,
        strip=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe el hallazgo, la actividad realizada o el estado actual.',
        }),
    )


class ConsumoRepuestoForm(forms.Form):
    repuesto = forms.ModelChoiceField(
        label='Repuesto o material',
        queryset=Repuesto.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    cantidad = forms.DecimalField(
        label='Cantidad utilizada',
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'step': '0.01',
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['repuesto'].queryset = Repuesto.objects.filter(
            activo=True,
            existencia__gt=0,
        ).order_by('codigo')


class RepuestoForm(forms.ModelForm):
    class Meta:
        model = Repuesto
        fields = ['codigo', 'nombre', 'unidad_medida']
        widgets = {
            'codigo': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'unidad_medida': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'pieza, litro, metro...',
            }),
        }

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        existentes = Repuesto.objects.filter(codigo__iexact=codigo)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError('Ya existe un repuesto con ese código.')
        return codigo


class EntradaRepuestoForm(forms.Form):
    cantidad = forms.DecimalField(
        label='Cantidad recibida',
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'step': '0.01',
        }),
    )
