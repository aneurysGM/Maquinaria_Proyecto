from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from apps.cuentas.models import UsuarioPersonalizado


class MiPerfilForm(forms.ModelForm):
    class Meta:
        model = UsuarioPersonalizado
        fields = ('first_name', 'last_name', 'telefono')
        labels = {'first_name': 'Nombre', 'last_name': 'Apellido', 'telefono': 'Teléfono'}
        widgets = {
            'first_name': forms.TextInput(attrs={'autocomplete': 'given-name'}),
            'last_name': forms.TextInput(attrs={'autocomplete': 'family-name'}),
            'telefono': forms.TextInput(attrs={'autocomplete': 'tel'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class CambioCorreoForm(forms.Form):
    correo_nuevo = forms.EmailField(
        label='Correo nuevo', max_length=254,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}),
    )
    contrasena_actual = forms.CharField(
        label='Contraseña actual', strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control', 'autocomplete': 'current-password',
        }),
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_correo_nuevo(self):
        correo = self.cleaned_data['correo_nuevo'].lower()
        if correo.casefold() == self.usuario.email.casefold():
            raise forms.ValidationError('Escribe un correo diferente del actual.')
        if UsuarioPersonalizado.objects.filter(email__iexact=correo).exists():
            raise forms.ValidationError('Ese correo ya está registrado.')
        return correo

    def clean_contrasena_actual(self):
        contrasena = self.cleaned_data['contrasena_actual']
        if not self.usuario.check_password(contrasena):
            raise forms.ValidationError('La contraseña actual es incorrecta.')
        return contrasena


class CambioContrasenaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
