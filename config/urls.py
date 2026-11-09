"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from apps.inventario.views import CatalogoPublicoView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='publico/index.html'), name='index'),
    path('catalogo/', CatalogoPublicoView.as_view(), name='catalogo'),
    path('ventas/', include('apps.ventas.urls')),
    # Rutas de la app cuentas (prefijo /cuentas/ o directamente en la raíz)
    path('auth/', include('apps.cuentas.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('alquileres/', include('apps.alquileres.urls')),
    path('mantenimiento/', include('apps.mantenimiento.urls')),
    path('reportes/', include('apps.reportes.urls')),
    path('clientes/', include('apps.clientes.urls')),
]