from django.contrib.auth.forms import UserCreationForm
from django import forms

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado


class TecnicoCreacionForm(UserCreationForm):
    first_name = forms.CharField(
        label='Nombre',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'name'}),
    )
    last_name = forms.CharField(
        label='Apellido',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'family-name'}),
    )
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'tel'}),
    )
    especialidad = forms.CharField(
        label='Especialidad',
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta(UserCreationForm.Meta):
        model = UsuarioPersonalizado
        fields = ('first_name', 'last_name', 'email', 'telefono', 'especialidad')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        tecnico = super().save(commit=False)
        tecnico.rol = RolUsuario.TECNICO
        tecnico.primer_inicio_sesion = True
        if commit:
            tecnico.save()
        return tecnico
