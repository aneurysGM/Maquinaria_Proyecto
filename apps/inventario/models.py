from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.conf import settings
from django.db import models
from django.utils import timezone


def anio_actual():
    return timezone.now().year


class Categoria(models.Model):
    id = models.AutoField(primary_key=True, db_column='CategoriaID')
    nombre = models.CharField(max_length=80, unique=True, db_column='Nombre')
    descripcion = models.CharField(
        max_length=200, blank=True, null=True, db_column='Descripcion'
    )

    class Meta:
        db_table = 'Categoria'
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'
        ordering = ('nombre',)

    def __str__(self):
        return self.nombre


class Maquinaria(models.Model):
    id = models.AutoField(primary_key=True, db_column='EquipoID')
    categoria = models.ForeignKey(
        Categoria,
        models.PROTECT,
        db_column='CategoriaID',
        related_name='maquinarias',
        verbose_name='Categoría'
    )
    codigo = models.CharField(max_length=20, unique=True, db_column='Codigo', verbose_name='Código')
    nombre = models.CharField(max_length=120, db_column='Nombre', verbose_name='Descripción')
    descripcion = models.TextField(blank=True, default='', verbose_name='Detalles del equipo')
    marca = models.CharField(max_length=60, blank=True, null=True, db_column='Marca')
    modelo = models.CharField(max_length=60, blank=True, null=True, db_column='Modelo')
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.SET_NULL,
        null=True,
        blank=True,
        related_name='maquinarias_registradas',
        verbose_name='Registrada por',
    )
    costo_adquisicion = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=(MinValueValidator(0),),
        db_column='CostoAdquisicion',
        verbose_name='Costo de adquisición'
    )
    tarifa_diaria = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
        db_column='TarifaDiaria',
        verbose_name='Tarifa diaria ($)'
    )
    tarifa_semanal = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
        db_column='TarifaSemanal',
        verbose_name='Tarifa semanal ($)'
    )
    tarifa_mensual = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=(MinValueValidator(0.01),),
        db_column='TarifaMensual',
        verbose_name='Tarifa mensual ($)'
    )
    deposito_garantia = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        validators=(MinValueValidator(0),),
        db_column='DepositoGarantia',
        verbose_name='Depósito de garantía ($)'
    )
    activo = models.BooleanField(default=True, db_column='Activo', verbose_name='Activo')
    fecha_modificacion = models.DateTimeField(
        blank=True, null=True, auto_now=True, db_column='FechaModificacion'
    )

    class Meta:
        db_table = 'Maquinaria'
        verbose_name = 'maquinaria'
        verbose_name_plural = 'maquinarias'
        ordering = ('codigo',)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(costo_adquisicion__gte=0),
                name='CK_Maquinaria_Costo_NoNegativo',
            ),
            models.CheckConstraint(
                condition=models.Q(tarifa_diaria__gt=0),
                name='CK_Maquinaria_TarifaDiaria_Positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(tarifa_semanal__gt=0),
                name='CK_Maquinaria_TarifaSemanal_Positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(tarifa_mensual__gt=0),
                name='CK_Maquinaria_TarifaMensual_Positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(deposito_garantia__gte=0),
                name='CK_Maquinaria_Deposito_NoNegativo',
            ),
        )

    def __str__(self):
        return f'{self.codigo} - {self.nombre}'


class MaquinariaImagen(models.Model):
    maquinaria = models.ForeignKey(
        Maquinaria,
        on_delete=models.CASCADE,
        related_name='imagenes',
        verbose_name='Maquinaria',
    )
    imagen = models.ImageField(upload_to='maquinaria/%Y/%m/')
    texto_alternativo = models.CharField(max_length=160, blank=True)

    class Meta:
        verbose_name = 'imagen de maquinaria'
        verbose_name_plural = 'imágenes de maquinaria'
        ordering = ('id',)


class MaquinariaComentario(models.Model):
    maquinaria = models.ForeignKey(
        Maquinaria,
        on_delete=models.CASCADE,
        related_name='comentarios',
        verbose_name='Maquinaria',
    )
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='comentarios_maquinaria',
        verbose_name='Cliente',
    )
    texto = models.TextField(max_length=1000)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'comentario de maquinaria'
        verbose_name_plural = 'comentarios de maquinaria'
        ordering = ('-creado_en', '-id')


class Unidad(models.Model):
    ESTADOS = (
        ('Disponible', 'Disponible'),
        ('Alquilado', 'Alquilado'),
        ('Mantenimiento', 'En mantenimiento'),
        ('Baja', 'Fuera de servicio'),
    )

    id = models.AutoField(primary_key=True, db_column='UnidadID')
    maquinaria = models.ForeignKey(
        Maquinaria,
        models.PROTECT,
        db_column='EquipoID',
        related_name='unidades',
        verbose_name='Maquinaria base'
    )
    numero_serie = models.CharField(
        max_length=50, unique=True, db_column='NumeroSerie', verbose_name='Número de serie'
    )
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default='Disponible', db_column='Estado', verbose_name='Estado'
    )
    horas_uso = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        validators=(MinValueValidator(0),),
        db_column='HorasUso',
        verbose_name='Horas de uso'
    )
    fecha_adquisicion = models.DateField(
        blank=True, null=True, db_column='FechaAdquisicion', verbose_name='Fecha de adquisición'
    )
    activo = models.BooleanField(default=True, db_column='Activo', verbose_name='Activa')
    ubicacion_actual = models.CharField(
        max_length=200, blank=True, null=True, db_column='UbicacionActual', verbose_name='Ubicación actual'
    )
    anio_fabricacion = models.PositiveSmallIntegerField(
        'Año de fabricación',
        blank=True,
        null=True,
        db_column='AnioFabricacion',
        validators=(MinValueValidator(1), MaxValueValidator(anio_actual)),
    )
    identificador_legacy = models.UUIDField(
        blank=True, null=True, unique=True, db_column='IdentificadorLegacy'
    )
    fecha_modificacion = models.DateTimeField(
        blank=True, null=True, auto_now=True, db_column='FechaModificacion'
    )

    class Meta:
        db_table = 'Unidad'
        verbose_name = 'unidad de maquinaria'
        verbose_name_plural = 'unidades de maquinaria'
        ordering = ('maquinaria__codigo', 'numero_serie')

    def __str__(self):
        return f'{self.maquinaria.codigo} / Serie: {self.numero_serie}'

    def clean(self):
        super().clean()
        if self._state.adding and not (self.ubicacion_actual or '').strip():
            raise ValidationError({
                'ubicacion_actual': 'La ubicación actual es obligatoria en registros nuevos.'
            })
        if self.pk and self.estado != 'Alquilado' and self.solicitudes_alquiler.filter(
            fecha_salida__isnull=False, fecha_retorno__isnull=True,
        ).exists():
            raise ValidationError({
                'estado': 'La unidad tiene una entrega pendiente. Registra su retorno para cambiar el estado.'
            })

    # Propiedades de conveniencia heredadas de la maquinaria base
    @property
    def codigo(self):
        return self.maquinaria.codigo

    @property
    def nombre(self):
        return self.maquinaria.nombre
