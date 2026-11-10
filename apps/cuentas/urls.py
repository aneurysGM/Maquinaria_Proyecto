from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views


app_name = "cuentas"

urlpatterns = [
    path('login/', views.IniciarSesionView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='index'), name='logout'),
    path('registro/', views.RegistrarClienteView.as_view(), name='registro'),
    path('contrasena/cambiar/', views.CambiarContrasenaView.as_view(), name='cambiar_contrasena'),
    path('dashboard/', views.DashboardAdminView.as_view(), name='dashboard'),
]