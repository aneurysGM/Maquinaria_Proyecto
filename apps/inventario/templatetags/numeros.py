from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def entero_con_comas(valor):
    if valor in (None, ''):
        return ''
    try:
        entero = Decimal(str(valor)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return ''
    return f'{int(entero):,}'
