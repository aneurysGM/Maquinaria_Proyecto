from django import forms

from apps.form_utils import GroupedIntegerField, GroupedIntegerWidget
from .models import PagoAlquiler, ReembolsoDeposito, ReembolsoRenta


class MotivosReservaForm(forms.Form):
    use_required_attribute = False
    def __init__(self, afectadas, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for solicitud in afectadas:
            self.fields[f'motivo_{solicitud.pk}'] = forms.CharField(
                label='Motivo para el cliente', max_length=1000,
                widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            )


class PagoAlquilerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['monto'] = None

    class Meta:
        model = PagoAlquiler
        fields = ['concepto', 'monto', 'metodo', 'referencia']
        widgets = {
            'concepto': forms.Select(attrs={'class': 'form-select'}),
            'monto': GroupedIntegerWidget(attrs={'class': 'form-control', 'min': '0'}),
            'metodo': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de recibo o referencia (opcional)',
            }),
        }
        field_classes = {'monto': GroupedIntegerField}


class ReembolsoDepositoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial['monto'] = None

    class Meta:
        model = ReembolsoDeposito
        fields = ['monto', 'metodo', 'referencia']
        widgets = {
            'monto': GroupedIntegerWidget(attrs={'class': 'form-control', 'min': '0'}),
            'metodo': forms.Select(attrs={'class': 'form-select'}),
            'referencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de recibo o referencia (opcional)',
            }),
        }
        field_classes = {'monto': GroupedIntegerField}


class ReembolsoRentaForm(ReembolsoDepositoForm):
    class Meta(ReembolsoDepositoForm.Meta):
        model = ReembolsoRenta
