from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from .models import UsuarioPersonalizado


class CorreoAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'autocomplete': 'email',
            'placeholder': 'nombre@correo.com',
        }),
    )


class RegistroClienteForm(UserCreationForm):
    """
    Formulario de registro para nuevos clientes que captura correo, 
    teléfono, nombre, apellido y contraseña.
    """
    first_name = forms.CharField(
        label='Nombre',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu nombre'})
    )
    last_name = forms.CharField(
        label='Apellido',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu apellido'})
    )
    email = forms.EmailField(
        label='Correo electrónico',
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'nombre@correo.com'})
    )
    telefono = forms.CharField(
        label='Teléfono',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(809) 000-0000'})
    )
    class Meta(UserCreationForm.Meta):
        model = UsuarioPersonalizado
        fields = ('first_name', 'last_name', 'email', 'telefono')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Comprobamos si es el primer usuario registrado en todo el sistema
        if not UsuarioPersonalizado.objects.exists():
            user.rol = 'Administrador'
            user.is_staff = True
            user.is_superuser = True
        else:
            user.rol = 'Cliente'
            
        if commit:
            user.save()
            self.save_m2m()
        return user