from django import forms

from .models import PagoAlquiler, ReembolsoDeposito


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
