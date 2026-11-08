from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class RolUsuario(models.TextChoices):
    ADMINISTRADOR = 'Administrador', 'Administrador'
    CLIENTE = 'Cliente', 'Cliente'
    TECNICO = 'Técnico', 'Técnico'
    TERCERO = 'Tercero', 'Dueño Externo / Tercero'


class UsuarioPersonalizadoManager(BaseUserManager):
    """
    Manager personalizado para manejar la creación de usuarios usando el email
    como identificador único en lugar del username tradicional.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El campo de Correo Electrónico es obligatorio')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class UsuarioPersonalizado(AbstractUser):
    """
    Modelo de usuario personalizado que utiliza el email como campo de inicio de sesión
    y soporta los roles del sistema de maquinaria pesada.
    """
    username = None
    
    email = models.EmailField(unique=True, verbose_name='Correo electrónico', db_column='Email')
    
    rol = models.CharField(
        max_length=30,
        choices=RolUsuario.choices,
        default=RolUsuario.CLIENTE,
        verbose_name='Rol del sistema',
        db_column='Rol'
    )
    telefono = models.CharField(
        max_length=20, 
        blank=True, 
        null=True, 
        verbose_name='Teléfono',
        db_column='Telefono'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UsuarioPersonalizadoManager()

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        db_table = 'Usuario'

    def __str__(self):
        return f'{self.email} ({self.get_rol_display()})'

    @property
    def es_administrador(self):
        return self.is_superuser or self.rol == RolUsuario.ADMINISTRADOR

    @property
    def es_cliente(self):
        return self.rol == RolUsuario.CLIENTE

    @property
    def es_tecnico(self):
        return self.rol == RolUsuario.TECNICO

    @property
    def es_tercero(self):
        return self.rol == RolUsuario.TERCERO

    @property
    def puede_consultar_maquinaria(self):
        return self.is_authenticated and self.is_active and (
            self.es_administrador or self.es_cliente or self.es_tecnico
        )

    @property
    def puede_registrar_maquinaria(self):
        return self.puede_consultar_maquinaria and self.es_administrador


class PerfilCliente(models.Model):
    """Datos de identidad específicos para los usuarios que actúan como clientes."""
    
    usuario = models.OneToOneField(
        UsuarioPersonalizado,
        on_delete=models.CASCADE,
        related_name='perfil_cliente',
        db_column='UsuarioID'
    )
    
    creado_en = models.DateTimeField(auto_now_add=True, db_column='CreadoEn')

    class Meta:
        verbose_name = 'perfil de cliente'
        verbose_name_plural = 'perfiles de clientes'
        db_table = 'PerfilCliente'

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class AutorizacionCliente(models.Model):
    """Control de permisos específicos que un administrador otorga a un cliente."""

    usuario = models.OneToOneField(
        UsuarioPersonalizado,
        on_delete=models.CASCADE,
        related_name='autorizacion_cliente',
        db_column='UsuarioID'
    )
    puede_editar_perfil = models.BooleanField(
        'Puede editar sus datos personales', default=False, db_column='PuedeEditarPerfil'
    )
    puede_solicitar_alquileres = models.BooleanField(
        'Puede solicitar alquileres', default=True, db_column='PuedeSolicitarAlquileres'
    )
    notas_internas = models.TextField('Notas internas', blank=True, db_column='NotasInternas')
    modificado_por = models.ForeignKey(
        UsuarioPersonalizado,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        db_column='ModificadoPorID'
    )
    modificado_en = models.DateTimeField(auto_now=True, db_column='ModificadoEn')

    class Meta:
        verbose_name = 'autorización de cliente'
        verbose_name_plural = 'autorizaciones de clientes'
        db_table = 'AutorizacionCliente'

    def __str__(self):
        return f'Autorizaciones de {self.usuario.email}'


def cliente_puede(usuario, permiso):
    """Evalúa si un cliente específico tiene autorizado realizar una acción."""
    if not usuario.is_authenticated:
        return False
    if usuario.es_administrador:
        return True
    autorizacion = getattr(usuario, 'autorizacion_cliente', None)
    return bool(autorizacion and getattr(autorizacion, permiso, False))


def permisos_panel(usuario):
    """Calcula y retorna un diccionario con los permisos del usuario para las plantillas."""
    if not usuario.is_authenticated or not usuario.is_active:
        return {}

    es_admin = usuario.es_administrador
    es_cli = usuario.es_cliente
    es_tec = usuario.es_tecnico
    es_ter = usuario.es_tercero
    puede_consultar = usuario.puede_consultar_maquinaria
    puede_registrar = usuario.puede_registrar_maquinaria

    return {
        'nombre_usuario': usuario.get_full_name() or usuario.email,
        'rol_usuario': usuario.get_rol_display(),
        'es_administrador': es_admin,
        'es_cliente': es_cli,
        'es_tecnico': es_tec,
        'es_tercero': es_ter,
        'puede_consultar_maquinaria': puede_consultar,
        'puede_registrar_maquinaria': puede_registrar,
        'puede_gestionar_clientes': es_admin,
    }


def contexto_panel(request):
    """Context processor global para inyectar permisos en todas las vistas."""
    if request.user.is_authenticated:
        return permisos_panel(request.user)
    return {}