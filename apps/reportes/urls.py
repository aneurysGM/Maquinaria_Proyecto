from django.urls import path

from . import reportes


app_name = 'reportes'

urlpatterns = [
    path('', reportes.indice, name='indice'),
    path('<slug:tipo>/', reportes.reporte, name='reporte'),
]
