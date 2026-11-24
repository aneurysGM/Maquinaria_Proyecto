from django import forms
from django.core.exceptions import ValidationError


class GroupedIntegerWidget(forms.TextInput):
    input_type = 'text'

    def __init__(self, attrs=None):
        base_attrs = {
            'inputmode': 'numeric',
            'pattern': '[0-9,]*',
            'autocomplete': 'off',
            'data-integer-input': '',
        }
        if attrs:
            base_attrs.update(attrs)
        super().__init__(attrs=base_attrs)


class GroupedIntegerField(forms.IntegerField):
    widget = GroupedIntegerWidget

    def __init__(self, *args, empty_value=0, **kwargs):
        self.empty_value = empty_value
        kwargs.setdefault('required', False)
        kwargs.setdefault('min_value', 0)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return self.empty_value
        if isinstance(value, str):
            value = value.strip()
            if not all(caracter.isdigit() or caracter == ',' for caracter in value):
                raise ValidationError(
                    'Ingresa un número entero sin puntos ni decimales.',
                    code='invalid',
                )
            value = value.replace(',', '')
        return super().to_python(value)
