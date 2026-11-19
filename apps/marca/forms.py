from django import forms

from .models import Marca


class MarcaForm(forms.ModelForm):
    class Meta:
        model = Marca
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': 60,
                'placeholder': 'Ej. Caterpillar',
            }),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        coincidencias = Marca.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            coincidencias = coincidencias.exclude(pk=self.instance.pk)
        if coincidencias.exists():
            raise forms.ValidationError('Ya existe una marca con ese nombre.')
        return nombre
