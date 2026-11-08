from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _es_decimal_seguro(valor):
    return len(valor.as_tuple().digits) <= 15


def _valor_celda(celda, valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.replace(tzinfo=None)
        if valor.date() < date(1900, 1, 1):
            celda.value = valor.isoformat(sep=' ')
            celda.number_format = '@'
        else:
            celda.value = valor
            celda.number_format = 'dd/mm/yyyy hh:mm:ss'
    elif isinstance(valor, date):
        if valor < date(1900, 1, 1):
            celda.value = valor.isoformat()
            celda.number_format = '@'
        else:
            celda.value = valor
            celda.number_format = 'dd/mm/yyyy'
    elif isinstance(valor, Decimal):
        if _es_decimal_seguro(valor):
            celda.value = valor
            celda.number_format = '#,##0.00'
        else:
            celda.value = format(valor, 'f')
            celda.number_format = '@'
    elif isinstance(valor, (int, float)):
        celda.value = valor
    elif valor is None:
        celda.value = ''
    else:
        texto = ILLEGAL_CHARACTERS_RE.sub('\uFFFD', str(valor))
        celda.value = texto
        celda.data_type = 's'
        celda.number_format = '@'

    celda.alignment = Alignment(vertical='top', wrap_text=True)


def exportar_excel(tipo, titulo, encabezados, filas, total):
    libro = Workbook()
    hoja = libro.active
    hoja.title = tipo[:31]

    for indice, encabezado in enumerate(encabezados, start=1):
        celda = hoja.cell(row=1, column=indice, value=encabezado)
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = PatternFill('solid', fgColor='1F2A33')
        celda.alignment = Alignment(vertical='center', wrap_text=True)

    for numero_fila, fila in enumerate(filas, start=2):
        for numero_columna, valor in enumerate(fila, start=1):
            _valor_celda(hoja.cell(row=numero_fila, column=numero_columna), valor)

    if total is not None:
        fila_total = len(filas) + 2
        celda = hoja.cell(row=fila_total, column=max(1, len(encabezados) - 1))
        celda.value = 'Total de costos'
        celda.font = Font(bold=True)
        celda = hoja.cell(row=fila_total, column=len(encabezados))
        _valor_celda(celda, total)
        celda.font = Font(bold=True)
        hoja.auto_filter.ref = f'A1:{get_column_letter(len(encabezados))}{len(filas) + 1}'
    elif encabezados:
        hoja.auto_filter.ref = f'A1:{get_column_letter(len(encabezados))}{len(filas) + 1}'

    hoja.freeze_panes = 'A2'
    hoja.row_dimensions[1].height = 30
    for numero_columna in range(1, len(encabezados) + 1):
        letra = get_column_letter(numero_columna)
        valores = [str(hoja.cell(row=fila, column=numero_columna).value or '')
                   for fila in range(1, hoja.max_row + 1)]
        hoja.column_dimensions[letra].width = min(max(max(map(len, valores), default=10) + 2, 12), 48)

    salida = BytesIO()
    libro.save(salida)
    salida.seek(0)
    response = HttpResponse(salida.getvalue(), content_type=CONTENT_TYPE)
    response['Content-Disposition'] = f'attachment; filename="reporte_{tipo}.xlsx"'
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response
