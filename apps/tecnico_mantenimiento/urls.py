from django.urls import path

from . import views


app_name = 'tecnico_mantenimiento'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('gestion/', views.lista, name='lista'),
    path('gestion/crear/', views.crear, name='crear'),
]
