from django import forms
from django.db import transaction
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from .models import (
    Categoria,
    Maquinaria,
    MaquinariaComentario,
    MaquinariaImagen,
    Unidad,
)


class MaquinariaComentarioForm(forms.ModelForm):
    class Meta:
        model = MaquinariaComentario
        fields = ['texto']
        widgets = {
            'texto': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'maxlength': 1000,
                'placeholder': 'Comparte tu experiencia con esta maquinaria...',
            }),
        }


class MaquinariaImagenForm(forms.ModelForm):
    class Meta:
        model = MaquinariaImagen
        fields = ['imagen', 'texto_alternativo']
        widgets = {
            'imagen': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'texto_alternativo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descripción breve de la imagen',
            }),
        }

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if imagen and imagen.size > 5 * 1024 * 1024:
            raise ValidationError('Cada imagen debe pesar 5 MB o menos.')
        return imagen


MaquinariaImagenFormSet = inlineformset_factory(
    Maquinaria,
    MaquinariaImagen,
    form=MaquinariaImagenForm,
    extra=2,
    can_delete=True,
    max_num=8,
    validate_max=True,
)

class MaquinariaIntegralForm(forms.ModelForm):
    # --- Campos inyectados para la Unidad Física ---
    numero_serie = forms.CharField(label='Número de serie', max_length=50, widget=forms.TextInput(attrs={'class': 'form-control'}))
    estado = forms.ChoiceField(label='Estado', choices=Unidad.ESTADOS, initial='Disponible', widget=forms.Select(attrs={'class': 'form-select'}))
    horas_uso = forms.DecimalField(label='Horas de uso', max_digits=10, decimal_places=1, initial=0, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}))
    fecha_adquisicion = forms.DateField(label='Fecha de adquisición', required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    anio_fabricacion = forms.IntegerField(label='Año de fabricación', required=False, widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1980'}))
    ubicacion_actual = forms.CharField(label='Ubicación actual', max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = Maquinaria
        fields = [
            'categoria', 'codigo', 'nombre', 'descripcion', 'marca', 'modelo',
            'costo_adquisicion', 'tarifa_diaria', 'tarifa_semanal',
            'tarifa_mensual', 'deposito_garantia'
        ]
        widgets = {
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'codigo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. GRU-001'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe las características principales de la maquinaria.',
            }),
            'marca': forms.TextInput(attrs={'class': 'form-control'}),
            'modelo': forms.TextInput(attrs={'class': 'form-control'}),
            'costo_adquisicion': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tarifa_diaria': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tarifa_semanal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tarifa_mensual': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'deposito_garantia': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos la instancia de 'unidad' si estamos en modo edición
        self.unidad_instancia = kwargs.pop('unidad', None)
        self.maquinaria_reactivada = None
        
        # Si pasaron una unidad, la instancia de Maquinaria base debe inyectarse en el ModelForm
        if self.unidad_instancia:
            kwargs['instance'] = self.unidad_instancia.maquinaria
            
        super().__init__(*args, **kwargs)

        # Precargar los datos de la unidad si estamos editando
        if self.unidad_instancia:
            self.fields['numero_serie'].initial = self.unidad_instancia.numero_serie
            self.fields['estado'].initial = self.unidad_instancia.estado
            self.fields['horas_uso'].initial = self.unidad_instancia.horas_uso
            self.fields['fecha_adquisicion'].initial = self.unidad_instancia.fecha_adquisicion
            self.fields['anio_fabricacion'].initial = self.unidad_instancia.anio_fabricacion
            self.fields['ubicacion_actual'].initial = self.unidad_instancia.ubicacion_actual

    def clean_numero_serie(self):
        numero_serie = self.cleaned_data['numero_serie']
        coincidencias = Unidad.objects.filter(numero_serie__iexact=numero_serie)
        
        if self.unidad_instancia:
            coincidencias = coincidencias.exclude(pk=self.unidad_instancia.pk)
            
        elif coincidencias.exists():
            codigo = self.data.get('codigo', '').strip()
            maquinaria_inactiva = Maquinaria.objects.filter(
                codigo__iexact=codigo,
                activo=False,
                unidades__numero_serie__iexact=numero_serie,
                unidades__activo=False,
            ).first()
            if maquinaria_inactiva:
                coincidencias = coincidencias.exclude(maquinaria=maquinaria_inactiva)

        if coincidencias.exists():
            raise ValidationError('Ya existe otra unidad registrada con este número de serie.')
        return numero_serie

    def clean_codigo(self):
        codigo = self.cleaned_data['codigo'].strip()
        coincidencia = Maquinaria.objects.filter(codigo__iexact=codigo)

        if self.unidad_instancia:
            coincidencia = coincidencia.exclude(pk=self.unidad_instancia.maquinaria_id)

        maquinaria = coincidencia.first()
        if maquinaria:
            if maquinaria.activo or self.unidad_instancia:
                raise ValidationError('Ya existe una maquinaria registrada con este código.')
            self.maquinaria_reactivada = maquinaria
            self.instance = maquinaria

        return codigo

    def clean(self):
        cleaned_data = super().clean()
        tarifa_diaria = cleaned_data.get('tarifa_diaria')
        tarifa_semanal = cleaned_data.get('tarifa_semanal')
        tarifa_mensual = cleaned_data.get('tarifa_mensual')

        if (
            tarifa_diaria is not None
            and tarifa_semanal is not None
            and tarifa_diaria >= tarifa_semanal
        ):
            self.add_error(
                'tarifa_semanal',
                'La tarifa semanal debe ser mayor que la tarifa diaria.',
            )

        if (
            tarifa_semanal is not None
            and tarifa_mensual is not None
            and tarifa_semanal >= tarifa_mensual
        ):
            self.add_error(
                'tarifa_mensual',
                'La tarifa mensual debe ser mayor que la tarifa semanal.',
            )

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        if self.maquinaria_reactivada:
            self.instance.activo = True

        # Guardar la Maquinaria (ModelForm nativo)
        maquinaria = super().save(commit=commit)
        
        if commit:
            # Crear o actualizar la Unidad física
            if self.unidad_instancia:
                unidad = self.unidad_instancia
                unidad.numero_serie = self.cleaned_data['numero_serie']
                unidad.estado = self.cleaned_data['estado']
                unidad.horas_uso = self.cleaned_data['horas_uso']
                unidad.fecha_adquisicion = self.cleaned_data['fecha_adquisicion']
                unidad.anio_fabricacion = self.cleaned_data['anio_fabricacion']
                unidad.ubicacion_actual = self.cleaned_data['ubicacion_actual']
                unidad.save()
            else:
                unidad = Unidad.objects.filter(
                    maquinaria=maquinaria,
                    numero_serie__iexact=self.cleaned_data['numero_serie'],
                ).first()
                if unidad:
                    unidad.activo = True
                    unidad.estado = self.cleaned_data['estado']
                    unidad.horas_uso = self.cleaned_data['horas_uso']
                    unidad.fecha_adquisicion = self.cleaned_data['fecha_adquisicion']
                    unidad.anio_fabricacion = self.cleaned_data['anio_fabricacion']
                    unidad.ubicacion_actual = self.cleaned_data['ubicacion_actual']
                    unidad.save()
                else:
                    Unidad.objects.create(
                        maquinaria=maquinaria,
                        numero_serie=self.cleaned_data['numero_serie'],
                        estado=self.cleaned_data['estado'],
                        horas_uso=self.cleaned_data['horas_uso'],
                        fecha_adquisicion=self.cleaned_data['fecha_adquisicion'],
                        anio_fabricacion=self.cleaned_data['anio_fabricacion'],
                        ubicacion_actual=self.cleaned_data['ubicacion_actual']
                    )
        return maquinaria

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Grúas, Excavadoras, etc.'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Breve descripción de la categoría'}),
        }
