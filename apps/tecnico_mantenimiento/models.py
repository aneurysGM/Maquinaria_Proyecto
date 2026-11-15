from django.db import models


class EspecialidadTecnica(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ('nombre',)
        verbose_name = 'especialidad técnica'
        verbose_name_plural = 'especialidades técnicas'

    def __str__(self):
        return self.nombre
