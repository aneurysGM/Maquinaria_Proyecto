from .models import EspecialidadTecnica


ESPECIALIDADES_BASE = ('Hidráulica', 'Electricidad', 'Mecánica')
NUEVA_ESPECIALIDAD = '__nueva__'


def opciones_especialidad():
    nombres = list(EspecialidadTecnica.objects.values_list('nombre', flat=True))
    extras = [nombre for nombre in nombres if nombre not in ESPECIALIDADES_BASE]
    return [(nombre, nombre) for nombre in (*ESPECIALIDADES_BASE, *extras)]


def guardar_especialidad(nombre):
    # Reutiliza el nombre del catálogo para evitar variantes por mayúsculas/espacios.
    for existente in EspecialidadTecnica.objects.all():
        if existente.nombre.casefold() == nombre.casefold():
            return existente.nombre
    especialidad, _ = EspecialidadTecnica.objects.get_or_create(nombre=nombre)
    return especialidad.nombre
