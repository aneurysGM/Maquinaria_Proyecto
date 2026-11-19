# Revisión de las acciones de categorías

Fecha: 19 de noviembre de 2026. Rama: `fix/acciones-maquinarias`.
Los cambios quedan locales para revisión y publicación por el responsable.

## Causa y reproducción

En **Maquinaria → Gestionar → Gestionar Categorías**
(`/inventario/categorias/`), el lápiz de cada fila tenía `href="#"`.
El navegador solo cambiaba el fragmento de la dirección: no enviaba una petición
de edición ni tenía una acción JavaScript asociada. Tampoco existían vistas o
rutas para editar o eliminar categorías. Por eso no aparecía ningún error.

Se reprodujo con una sesión de Administrador mediante el cliente de pruebas de
Django y dos categorías ficticias en SQLite temporal. Antes del arreglo, la
prueba de enlaces falló para ambas filas porque el destino era `#`.

## Cambios

- `apps/inventario/templates/inventario/categoria_lista.html`: el lápiz abre
  **Editar**, y un botón **Eliminar** abre la confirmación de esa misma fila.
  Los enlaces utilizan la clave de la categoría y no requieren JavaScript.
- `apps/inventario/urls.py`: añade
  `/inventario/categorias/<id>/editar/` y
  `/inventario/categorias/<id>/eliminar/`.
- `apps/inventario/views.py`: añade `CategoriaEditarView`, que reutiliza
  `CategoriaForm` y la plantilla de formulario existente; y
  `CategoriaEliminarView`, que muestra la confirmación en GET y elimina por
  POST con CSRF. Ambas reutilizan los permisos del Administrador y vuelven al
  listado con un mensaje de resultado.
- Archivo nuevo `apps/inventario/templates/inventario/categoria_confirmar_eliminar.html`:
  presenta nombre, descripción y equipos asociados. **Cancelar** vuelve al
  listado sin enviar el formulario. **Confirmar eliminación** solo está
  disponible si no hay maquinaria asociada.

La relación existente `Maquinaria.categoria` usa `PROTECT`. El servidor conserva
esa protección al confirmar y comunica el motivo si hay equipos, aunque estén
inactivos o se hayan asociado después de abrir la confirmación. El borrado no
modifica ni elimina maquinaria. No se cambiaron modelos ni migraciones.

## Comprobaciones realizadas

Las 12 pruebas nuevas de
`test/django/inventario/tests_categorias.py` pasaron en SQLite temporal:

- Enlaces de dos filas distintas y formulario precargado con los datos correctos.
- Guardado de nombre y descripción, cambio visible en el listado, mensaje de
  éxito y conservación de la otra categoría.
- Errores por nombre vacío, duplicado o demasiado largo sin guardar cambios;
  navegación de cancelación de la edición.
- Confirmación con los datos de la categoría seleccionada; apertura por GET y
  navegación de **Cancelar** sin eliminarla.
- POST de confirmación que elimina solo una categoría ficticia sin equipos.
- Bloqueo del borrado con maquinaria inactiva y con maquinaria asociada entre
  la apertura de la confirmación y el envío.
- Inicio de sesión obligatorio; rechazo de GET y POST para Cliente, Técnico,
  Tercero y usuario sin rol; CSRF; rechazo de DELETE y categorías inexistentes.

```powershell
.\.venv\Scripts\python.exe -B manage.py test test.django.inventario.tests_categorias --noinput --verbosity 2
.\.venv\Scripts\python.exe -B manage.py test test.django.inventario --noinput
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
git diff --check
```

`check`, la comprobación de migraciones y `diff --check` pasaron. La suite de
inventario ejecutó 34 pruebas y reportó cuatro fallos anteriores en
`CatalogoPanelTests`: una expectativa de ausencia de barra lateral en
`test_cliente_ve_tarifas_y_deposito_pero_no_costo_adquisicion` y tres subcasos
por rol de `test_detalle_desde_catalogo_no_muestra_panel_lateral_a_ningun_rol`.
Una copia temporal de HEAD, sin este arreglo, ejecutó las 22 pruebas existentes
y reprodujo exactamente esos mismos fallos. No aparecieron fallos nuevos.

Los datos ficticios se crearon y eliminaron únicamente en las bases de pruebas;
no se editaron las categorías de `db.sqlite3`. Las pruebas y las evidencias
permanecen en `test/`, excluido de Git por la configuración del proyecto.
`test/evidencias/categorias_comparacion.json` y los registros
`categorias_base.log` y `categorias_corregida.log` conservan la comparación;
`test/evidencias/verificar_categorias_base.py` permite repetirla sin modificar
el checkout actual.

## Revisión visual

El usuario confirmó que probó el arreglo en Edge y quedó bien, con **Editar** y
**Eliminar** visibles en cada fila de **Gestionar Categorías**. Las pruebas
automatizadas anteriores verificaron las respuestas del servidor y el HTML.
No se ejecutó contra SQL Server; esta copia utiliza SQLite.

Para repetir la comprobación en el navegador:

1. Iniciar sesión como Administrador y abrir **Gestionar Categorías**.
2. Crear una categoría desechable, por ejemplo `QA Categoría revisión`, con una
   descripción reconocible y sin equipos asociados.
3. Pulsar su lápiz **Editar**. Comprobar nombre y descripción, cambiar ambos y
   guardar. Confirmar el mensaje y los nuevos valores en el listado; volver a
   abrir para comprobar que persistieron.
4. Pulsar **Eliminar** en esa fila. Revisar el nombre mostrado, pulsar
   **Cancelar** y recargar el listado: la categoría debe conservarse.
5. Volver a pulsar **Eliminar** y **Confirmar eliminación** sobre esa categoría
   desechable. Debe aparecer el mensaje de éxito y desaparecer la fila.
6. Abrir **Eliminar** en una categoría con equipos: debe informar del bloqueo
   y ofrecer volver al listado sin mostrar el botón de confirmación.
