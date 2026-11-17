from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.db import transaction

from apps.cuentas.models import RolUsuario, UsuarioPersonalizado
from .especialidades import NUEVA_ESPECIALIDAD, guardar_especialidad, opciones_especialidad


class EspecialidadFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = opciones_especialidad()
        actual = self.initial.get('especialidad')
        if actual and actual not in dict(opciones):
            opciones.append((actual, actual))
        self.fields['especialidad'].choices = [
            ('', 'Selecciona una especialidad'), *opciones,
            (NUEVA_ESPECIALIDAD, '+ Añadir especialidad'),
        ]
        orden = [campo for campo in self.fields if campo != 'nueva_especialidad']
        orden.insert(orden.index('especialidad') + 1, 'nueva_especialidad')
        self.order_fields(orden)

    def clean(self):
        datos = super().clean()
        if datos.get('especialidad') == NUEVA_ESPECIALIDAD:
            nombre = ' '.join(datos.get('nueva_especialidad', '').split())
            if not nombre:
                self.add_error('nueva_especialidad', 'Escribe la nueva especialidad.')
                datos.pop('especialidad', None)
            elif nombre == NUEVA_ESPECIALIDAD:
                self.add_error('nueva_especialidad', 'Elige otro nombre para la especialidad.')
                datos.pop('especialidad', None)
            else:
                datos['especialidad'] = nombre
        return datos

    @transaction.atomic
    def save(self, commit=True):
        tecnico = super().save(commit=False)
        if commit:
            if tecnico.especialidad:
                tecnico.especialidad = guardar_especialidad(tecnico.especialidad)
            tecnico.save()
        return tecnico


class TecnicoCreacionForm(EspecialidadFormMixin, UserCreationForm):
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
    especialidad = forms.ChoiceField(
        label='Especialidad',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    nueva_especialidad = forms.CharField(
        label='Nueva especialidad', max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )

    class Meta(UserCreationForm.Meta):
        model = UsuarioPersonalizado
        fields = ('first_name', 'last_name', 'email', 'telefono', 'especialidad')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    @transaction.atomic
    def save(self, commit=True):
        self.instance.rol = RolUsuario.TECNICO
        self.instance.primer_inicio_sesion = True
        return super().save(commit=commit)


class TecnicoPerfilForm(EspecialidadFormMixin, forms.ModelForm):
    especialidad = forms.ChoiceField(
        label='Especialidad', required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    nueva_especialidad = forms.CharField(
        label='Nueva especialidad', max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    disponible = forms.TypedChoiceField(
        label='Disponibilidad', choices=(('1', 'Disponible'), ('0', 'No disponible')),
        coerce=lambda valor: valor == '1',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = UsuarioPersonalizado
        fields = ('especialidad', 'disponible')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial['disponible'] = '1' if self.instance.disponible else '0'
