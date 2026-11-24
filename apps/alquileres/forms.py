from django import forms
from django.utils import timezone
from apps.cuentas.models import DireccionCliente
from apps.configuraciones.forms import DireccionClienteForm
from apps.form_utils import GroupedIntegerField, GroupedIntegerWidget
from .models import SolicitudAlquiler


class DireccionEntregaForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=(('guardada', 'Guardada'), ('nueva', 'Nueva')),
        widget=forms.HiddenInput,
    )
    direccion_guardada = forms.ModelChoiceField(
        label='Dirección guardada', queryset=DireccionCliente.objects.none(), required=False,
        empty_label=None, widget=forms.RadioSelect(attrs={'class': 'form-check-input flex-shrink-0'}),
    )
    direccion = forms.CharField(
        label='Dirección completa', max_length=500, required=False,
        widget=DireccionClienteForm.Meta.widgets['direccion'],
    )
    referencia = forms.CharField(
        label='Referencia (opcional)', max_length=300, required=False,
        widget=DireccionClienteForm.Meta.widgets['referencia'],
    )
    guardar = forms.BooleanField(
        label='Guardar para futuros alquileres', required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    nombre = forms.CharField(
        label='Nombre de la dirección', max_length=100, required=False,
        widget=DireccionClienteForm.Meta.widgets['nombre'],
    )

    def __init__(self, *args, cliente, tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['direccion_guardada'].queryset = DireccionCliente.objects.filter(cliente=cliente)
        self.tiene_guardadas = self.fields['direccion_guardada'].queryset.exists()
        self.modo = (
            self.data.get('tipo') if self.is_bound
            else ('nueva' if tipo == 'nueva' or not self.tiene_guardadas else 'guardada')
        )
        if self.modo not in ('nueva', 'guardada'):
            self.modo = 'nueva'
        self.initial['tipo'] = self.modo
        if self.modo == 'nueva':
            self.fields['direccion'].required = True
        else:
            self.fields['direccion_guardada'].required = True

    def clean(self):
        datos = super().clean()
        if datos.get('tipo') == 'nueva' and datos.get('guardar') and not datos.get('nombre'):
            self.add_error('nombre', 'Asigna un nombre para guardar la dirección.')
        return datos


class SolicitudAlquilerForm(forms.ModelForm):
    cantidad = GroupedIntegerField(
        label='Cantidad de planes',
        min_value=0,
        widget=GroupedIntegerWidget(attrs={'class': 'form-control', 'min': '0'}),
    )

    class Meta:
        model = SolicitudAlquiler
        fields = ['fecha_inicio', 'plan', 'cantidad', 'comentario']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'plan': forms.Select(attrs={'class': 'form-select'}),
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

        return cleaned_data


class SolicitudAplazarForm(forms.Form):
    fecha_inicio = forms.DateField(
        label='Nueva fecha de inicio',
        input_formats=['%Y-%m-%d'],
        widget=forms.DateInput(attrs={
            'class': 'form-control form-control-sm',
            'type': 'date',
        }),
    )

    def clean_fecha_inicio(self):
        fecha_inicio = self.cleaned_data['fecha_inicio']
        if fecha_inicio < timezone.localdate():
            raise forms.ValidationError('La nueva fecha de inicio no puede estar en el pasado.')
        return fecha_inicio


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
    horas_uso_actualizadas = GroupedIntegerField(
        min_value=0,
        empty_value=None,
        widget=GroupedIntegerWidget(attrs={'class': 'form-control'}),
        label='Horas de uso totales del horómetro'
    )
    observaciones_retorno = forms.CharField(
        required=False,
        max_length=1000,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Estado en el que regresa la máquina, daños o observaciones.'}),
        label='Observaciones de retorno'
    )
