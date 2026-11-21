# Dirección de entrega del Cliente

Rama `feat/direccion-entrega-cliente`, creada desde `origin/main` actualizado
(`83db721`).

## Comportamiento y acceso

Se reutiliza `pago_inicial_completo`: renta y depósito completos, igual que en
la confirmación actual de reserva. No cambia cómo se registra el pago ni su
`fecha_confirmacion`. Una solicitud aprobada, pagada y sin salida muestra
**Pendiente de dirección de entrega** y **Indicar dirección de entrega** en
Mis alquileres y su detalle. El presupuesto también ofrece el acceso después
del pago. El estado depende de datos persistidos; cerrar la página o sesión
no pierde el paso.

Sin direcciones propias guardadas se abre directamente Dirección nueva. Con
direcciones, se pueden elegir mediante tarjetas con su texto completo y
referencia, o cambiar a Escribir dirección nueva. La dirección admite 500
caracteres y la referencia opcional admite 300. **Guardar para futuros alquileres**
permite asignar un nombre de hasta 100 caracteres, obligatorio al guardar, como
**Obra en San Luis**. Sin marcarla, solo se guarda en este alquiler. Sin JavaScript
el nombre permanece visible y el servidor mantiene la validación condicional.

Configuraciones → Mis direcciones permite agregar, editar y eliminar las
direcciones propias. El borrado muestra confirmación y solo se ejecuta por POST.
Al confirmar la entrega se copian dirección, referencia, nombre y fecha al
alquiler. No existe una relación editable con la libreta: editar o borrar una
dirección guardada no altera la copia. Reenviar la confirmación tampoco sustituye
la copia ni duplica la dirección guardada.

El Administrador ve el aviso mientras falte la dirección y la copia completa
cuando esté confirmada. La salida requiere tanto el texto de dirección como
su fecha de confirmación. Se valida en el servidor incluso ante un POST directo.
Las demás condiciones de salida, como pago y fecha programada, siguen vigentes.

Las consultas de alquileres, presupuestos y direcciones del Cliente se filtran
por el usuario de la sesión. Enviar otro `cliente` por POST no cambia el titular.
Acceder a un alquiler o dirección ajena devuelve 404; elegir una dirección
guardada ajena produce un error de validación. Administrador y Técnico no pueden
confirmar la dirección por el Cliente ni administrar su libreta mediante estas
rutas. Las escrituras requieren CSRF.

La confirmación bloquea unidad → solicitud → dirección guardada, en el orden
que ya usan pagos y salidas. Relee el estado y la dirección dentro de la
transacción. La copia y la creación opcional en la libreta se guardan juntas;
si falla la copia, tampoco queda una dirección guardada a medias.

## Migraciones y alquileres anteriores

- `apps/cuentas/migrations/0008_direccioncliente.py`: crea la libreta con titular,
  nombre, dirección y referencia.
- `apps/alquileres/migrations/0007_solicitudalquiler_direccion_entrega_and_more.py`:
  agrega la copia y una fecha nullable. Los textos anteriores quedan vacíos;
  no se inventan fechas ni direcciones.

Los alquileres anteriores con salida mantienen **En uso** o **Devuelto**, no
solicitan una dirección retroactiva y muestran **Dirección no registrada
(alquiler anterior)**. Pueden registrar el retorno sin dirección. Los alquileres
pagados que aún no salieron deben indicarla, incluso si su pago es anterior a
`fecha_confirmacion`. Las solicitudes impagas mantienen su flujo habitual.

Las migraciones se probaron en bases temporales y en una copia de `db.sqlite3`:
las 33 tablas preexistentes conservaron todos sus valores y los 7 alquileres
anteriores quedaron sin direcciones inventadas. Durante esas comprobaciones no
se migró la base principal.
La validación de migraciones fue en SQLite; no se ejecutó contra SQL Server.

Para probar en la instalación habitual:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py runserver
```

## Prueba manual

1. Entrar como Cliente sin direcciones y solicitar un alquiler. Como Administrador,
   aprobarlo y registrar renta y depósito usando la revisión y confirmación de
   reserva actuales. Un pago parcial todavía no debe pedir dirección.
2. Como Cliente, abrir Mis alquileres → Ver detalle. Comprobar el aviso y el botón.
   Cerrar sesión o el navegador, volver a entrar y abrir el mismo alquiler:
   el aviso y el botón deben seguir disponibles.
3. Abrir Indicar dirección de entrega. Debe aparecer directamente Dirección nueva.
   Completar calle, número, sector, municipio y provincia, y una referencia.
   Marcar Guardar para futuros alquileres y asignar Obra en San Luis. Confirmar.
   Debe verse la dirección completa y el estado Pendiente de entrega.
4. Preparar otro alquiler pagado. Elegir Obra en San Luis y confirmar. Probar
   también Escribir dirección nueva, sin guardarla y sin referencia: no debe
   crearse otra entrada en Mis direcciones.
5. En Configuraciones → Mis direcciones, agregar otra dirección, editar Obra en
   San Luis y eliminarla. Cancelar primero la eliminación y luego confirmarla.
   Los alquileres deben conservar la copia original para Cliente y Administrador.
6. Como Administrador, comprobar el aviso antes de confirmar y la dirección
   completa después. Antes no debe mostrarse el botón de salida; un POST directo
   a `/alquileres/solicitudes/<id>/salida/` debe bloquearse. Después debe permitir
   registrar la salida si se cumplen las demás condiciones existentes.
7. Con otro Cliente, intentar abrir el detalle, presupuesto o formulario del
   primero, y editar/eliminar sus direcciones: debe devolver 404. Enviar una
   dirección guardada ajena debe producir un error y no confirmar la dirección.
8. Revisar un alquiler anterior con salida o retorno: debe conservar su estado,
   indicar que no tiene dirección registrada y no ofrecer el formulario nuevo.

## Verificación

- Pasan las 30 pruebas de `apps.alquileres`: las 6 existentes y 24 nuevas.
  Cubren pago mediante las vistas actuales, nueva/guardada, nueva sesión,
  referencia opcional, validación, propiedad, CRUD, CSRF, reversión ante fallo,
  reenvío, cambio de estado o eliminación de dirección durante la confirmación,
  salida bloqueada/habilitada e historial anterior.
- Pasan 74 pruebas seleccionadas de alquileres, marcas, órdenes, configuraciones
  y ventas. Parte de estas pruebas permanece en la carpeta local ignorada `test/`,
  como en el resto del proyecto. Las 24 nuevas están en el archivo versionado
  `apps/alquileres/tests.py`.
- Pasan `manage.py check`, `makemigrations --check --dry-run` y `git diff --check`.
- La comprobación JavaScript valida que la casilla oculta/deshabilita el nombre
  inicialmente, lo muestra y exige al marcarla, lo oculta al desmarcarla y no
  falla en el formulario de direcciones guardadas.
- Dos fallos ajenos a direcciones se reprodujeron en una copia limpia de `main`:
  cierres mensuales espera el texto antiguo «Cerrar mes y descargar Excel» y una
  prueba local de configuraciones espera un formulario con la acción antigua
  de cierre mensual. No se modificaron estas pruebas ni el módulo de cierres.
- La inspección visual en Edge quedó bloqueada por Computer Use al no poder
  determinar la URL actual. Se validó el HTML mediante Django. Posteriormente,
  el usuario confirmó manualmente que el Cliente puede confirmar la dirección,
  que el Administrador la ve en el alquiler y que queda guardada en Mis direcciones.

Para repetir las pruebas versionadas del flujo:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.alquileres --noinput
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

## Archivos modificados o nuevos

| Ruta | Propósito |
| --- | --- |
| `apps/cuentas/models.py` | Libreta con titular. |
| `apps/cuentas/migrations/0008_direccioncliente.py` | Tabla de direcciones. |
| `apps/alquileres/models.py` | Copia persistida y estado del Cliente. |
| `apps/alquileres/migrations/0007_solicitudalquiler_direccion_entrega_and_more.py` | Columnas de la copia. |
| `apps/alquileres/forms.py` | Dirección nueva o elección propia. |
| `apps/alquileres/views.py` | Confirmación atómica y validación de salida. |
| `apps/alquileres/urls.py` | Ruta de dirección de entrega. |
| `apps/alquileres/tests.py` | 24 pruebas nuevas de aceptación y acceso. |
| `apps/alquileres/static/alquileres/direccion_entrega.js` | Nombre visible al marcar Guardar. |
| `apps/alquileres/templates/alquileres/direccion_entrega_form.html` | Formulario con estilo de Mis alquileres. |
| `apps/alquileres/templates/alquileres/direccion_entrega_resumen.html` | Aviso, dirección e historial sin dirección. |
| `apps/alquileres/templates/alquileres/estado_cliente.html` | Distintivo de dirección pendiente. |
| `apps/alquileres/templates/alquileres/proximo_paso.html` | Orientación después del pago. |
| `apps/alquileres/templates/alquileres/solicitud_acciones.html` | Botón del Cliente y salida condicionada. |
| `apps/alquileres/templates/alquileres/solicitud_detalle.html` | Dirección para Cliente y Administrador. |
| `apps/ventas/templates/ventas/presupuesto_detalle.html` | Acceso tras confirmar el pago actual. |
| `apps/configuraciones/forms.py` | Formulario de direcciones guardadas. |
| `apps/configuraciones/views.py` | CRUD propio restringido al Cliente. |
| `apps/configuraciones/urls.py` | Rutas de Mis direcciones. |
| `apps/configuraciones/templates/configuraciones/indice.html` | Acceso a Mis direcciones. |
| `apps/configuraciones/templates/configuraciones/direccion_lista.html` | Lista de direcciones propias. |
| `apps/configuraciones/templates/configuraciones/direccion_form.html` | Alta y edición. |
| `apps/configuraciones/templates/configuraciones/direccion_confirmar_eliminar.html` | Confirmación de borrado. |
| `docs/direccion-entrega-cliente.md` | Guía y pasos de aceptación. |
| `README.md` | Registro del cambio y enlace a esta guía. |
