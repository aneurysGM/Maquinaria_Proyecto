# Asignación de técnicos a mantenimiento

La rama `feature/asignar-tecnico` incorpora especialidades compartidas, disponibilidad
y la separación entre quien registra un mantenimiento y su responsable.

## Uso

- En **Técnicos → Crear Nuevo Técnico**, Especialidad ofrece Hidráulica, Electricidad
  y Mecánica. **+ Añadir especialidad** permite escribir otra; se incorpora al
  catálogo al guardar correctamente el perfil y se puede reutilizar en otros
  perfiles y en el filtro de mantenimiento.
- Desde el nombre del técnico en el listado, el administrador abre su perfil y
  cambia la especialidad o marca **Disponible / No disponible**. La disponibilidad
  no desactiva la cuenta ni modifica su contraseña.
- Al registrar mantenimiento como administrador, **Registrado por** muestra al
  usuario de la sesión. El filtro limita la selección de **Técnico responsable**
  a cuentas de técnicos activas y disponibles. Sin filtro se ofrecen todas las
  cuentas elegibles; sin coincidencias aparece un aviso. Al cambiar el filtro se
  limpia cualquier selección incompatible. Sin JavaScript, **Aplicar filtro de
  especialidad** actualiza las opciones conservando los demás datos del formulario.
- El servidor exige un responsable válido y vuelve a verificar su rol, actividad,
  disponibilidad y especialidad dentro de la transacción de guardado.
- Al registrar como técnico, el responsable y el autor se obtienen de la sesión,
  aunque se envíe otro identificador en el formulario. **No disponible** limita las
  asignaciones del administrador; el técnico puede registrar su propio trabajo.
- La aceptación o el rechazo de solicitudes por técnicos queda pendiente.

## Migraciones y datos existentes

Ejecutar `python manage.py migrate` antes de iniciar la versión actualizada,
con un respaldo previo de la base de datos.

Las migraciones añaden `UsuarioPersonalizado.disponible` (inicialmente verdadero),
el catálogo `EspecialidadTecnica` y `Mantenimiento.registrado_por`. Se cargan las
tres especialidades base y las especialidades previas de los técnicos sin cambiar
sus perfiles. Se conserva el responsable histórico y se copia como autor porque
el flujo anterior guardaba allí al usuario que registraba el mantenimiento.
Los registros históricos sin responsable permanecen sin autor identificado.

En la copia local se respaldó SQLite antes de migrar y se compararon los valores
de todas las columnas previas de las 21 tablas existentes: se conservaron sus datos.
Django añadió los permisos y el tipo de contenido del nuevo catálogo.

## Verificación

```powershell
python manage.py test apps.tecnico_mantenimiento apps.mantenimiento --noinput
node apps/tecnico_mantenimiento/tests_controles.cjs
python manage.py makemigrations --check --dry-run
python manage.py check
```

Los 26 casos de técnicos/mantenimiento cubren ambos roles, selección manipulada,
cambios de disponibilidad entre validación y guardado, permisos, reutilización de
especialidades y migración con registros históricos. La prueba de JavaScript cubre
el campo condicional, filtrado, limpieza de selección y aviso de lista vacía.

La suite completa ejecuta 171 casos y conserva tres fallos ya presentes en `main`:
dos en `DashboardPendientesTests` y uno en
`DashboardAdministradorTests.test_ceros_y_listas_vacias`, relacionados con el HTML
del panel. `main` también tenía tres fallos de subcasos de la prueba del avatar;
esa comprobación se actualizó para contemplar su atributo `aria-hidden` existente.
La verificación visual quedó pendiente porque el navegador conectado no estaba
disponible en esta sesión.

## Publicación

Antes de cada publicación, verificar que `git branch --show-current` devuelve
`feature/asignar-tecnico` y ejecutar `git push origin feature/asignar-tecnico`.
La revisión se realiza mediante un Pull Request hacia `main`; la fusión queda a
criterio del compañero revisor.
