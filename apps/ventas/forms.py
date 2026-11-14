from django import forms

from .models import PagoAlquiler, ReembolsoDeposito


class MotivosReservaForm(forms.Form):
    use_required_attribute = False
    def __init__(self, afectadas, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for solicitud in afectadas:
            self.fields[f'motivo_{solicitud.pk}'] = forms.CharField(
                label='Motivo', max_length=1000,
                widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            )


class PagoAlquilerForm(forms.ModelForm):
    class Meta:
        model = PagoAlquiler
        fields = ['concepto', 'monto', 'metodo', 'referencia']
        widgets = {
            'concepto': forms.Select(attrs={'class': 'form-select'}),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.01', 'step': '0.01'
            }),
            'metodo': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de recibo o referencia (opcional)',
            }),
        }


class ReembolsoDepositoForm(forms.ModelForm):
    class Meta:
        model = ReembolsoDeposito
        fields = ['monto', 'metodo', 'referencia']
        widgets = {
            'monto': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0.01', 'step': '0.01'
            }),
            'metodo': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de recibo o referencia (opcional)',
            }),
        }
