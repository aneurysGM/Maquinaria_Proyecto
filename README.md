# Sistema de alquiler de equipos

Para obtener esta entrega desde GitHub y actualizar una instalación existente,
consulta la [guía de actualización e integración](docs/actualizacion-e-integracion.md).
Incluye el respaldo previo, las migraciones y los pasos de comprobación y arranque.

Proyecto Django con inicio de sesión y tres roles: Administrador, Cliente y
Técnico de mantenimiento. Incluye registro, edición y consulta de maquinaria,
mantenimiento por unidad y solicitudes de alquiler que revisa el administrador.
HU-09 añade salida y retorno físicos desde solicitudes aprobadas, con historial
y responsables administrativos. Ver [HU-09: salida y retorno](docs/hu09-salida-retorno.md).
La [revisión de alquileres y devoluciones](docs/revision-alquileres.md) documenta
el detalle por solicitud, los filtros administrativos, los avisos de vencimiento
y la organización de las pruebas en `usuarios/tests/`.
HU-10 incorpora [reportes administrativos](docs/hu10-reportes.md) de maquinaria,
solicitudes, salidas/retornos y mantenimiento, con filtros y descargas Excel
(.xlsx). El XLSX conserva columnas, identificadores como texto, fechas,
costos, filtros y encabezado inmovilizado.
La aplicación utiliza SQL Server. El módulo de operadores está retirado.

## Registro de cambios y documentación

Este README también sirve como bitácora del trabajo del proyecto. Al realizar
cambios importantes o arreglos relevantes, se debe añadir una nota que explique
qué cambió, por qué se hizo y qué comprobaciones se ejecutaron. Cuando se creen
archivos o carpetas, se deben identificar por su ruta y describir brevemente
su propósito. Los cambios pequeños que no alteren comportamiento ni estructura
no necesitan una entrada individual. Si el detalle requiere más espacio, se
puede documentar en una guía específica y enlazarla desde aquí.

### Estado final de las mejoras de alquiler — 13 de noviembre de 2026

- La última ejecución de Django pasó **150 pruebas en SQLite temporal**. Se
  incluyen las pruebas de reservas, rechazo manual, sugerencias de búsqueda y
  panel administrativo, además de los controles JavaScript del calendario,
  confirmación del pago y sugerencias de códigos.
- El rechazo manual queda a la derecha de Aprobar, en rojo sólido, y conserva la
  ventana de confirmación. El detalle del rechazo usa un recuadro ámbar claro.
  Pendiente de aprobación se muestra en amarillo; Pendiente de pago, en azul
  claro con texto azul oscuro; Devuelto, en gris carbón `#343A40` con texto blanco.
  En uso conserva el verde y la pestaña Devueltas conserva el azul.
- El código, la migración, las pruebas y la documentación se preparan para un
  commit local. El archivo `.env`, SQLite, sus respaldos y los temporales quedan
  fuera del control de versiones. La publicación de la rama se realiza aparte.

### Sugerencias de códigos en solicitudes recibidas — 13 de noviembre de 2026

- Buscar ofrece códigos de maquinaria mientras se escribe, sin distinguir
  mayúsculas y minúsculas y sin repetirlos. Usa únicamente solicitudes visibles
  que coinciden con el estado y las fechas seleccionados; no limita la cantidad
  de coincidencias. Si se escribe un código completo, muestra solo ese código.
- Elegir una sugerencia completa Buscar y envía el formulario con coincidencia
  exacta por código, conservando estado y fechas. Escribir otra consulta descarta
  la selección anterior. El botón Buscar y la búsqueda libre por cliente,
  maquinaria, serie o número de solicitud mantienen su comportamiento.
- `apps/alquileres/static/alquileres/sugerencias_codigos.js` controla el desplegable,
  la selección por ratón o teclado, Escape y las peticiones canceladas. La ruta
  `alquileres/solicitudes/sugerencias-codigos/` es de solo lectura y exclusiva del
  Administrador. Ante un error de red sigue disponible la búsqueda normal.
- `apps/alquileres/tests_sugerencias.py` añade siete pruebas con datos temporales
  para códigos, filtros, coincidencia exacta, duplicados y permisos.
  `apps/alquileres/tests_sugerencias_controles.cjs` verifica el control JavaScript
  con Node.js y un DOM mínimo, incluidas respuestas que llegan fuera de orden.
- Pasaron **86 pruebas de alquileres y del panel**, las comprobaciones JavaScript,
  `manage.py check`, `makemigrations --check --dry-run` y `git diff --check`.
  La comprobación local de solo lectura encontró la nueva solicitud de Luis #5
  (Aprobada) al seleccionar EXC-PR-002 y verificó los filtros de estado y fechas.
  El prefijo EXC-PR-00 devolvió EXC-PR-001 y EXC-PR-002; no había solicitudes
  visibles para EXC-PR-003. Solicitudes, presupuestos, pagos y reembolsos intactos.

### Panel del Administrador conectado a datos reales — 13 de noviembre de 2026

- `/auth/dashboard/` conserva su diseño y el conteo de equipos disponibles del
  inventario administrativo. Las solicitudes pendientes comparten consulta y
  total entre tarjeta y pestaña; cada enlace Revisar abre su solicitud concreta.
  Alquileres activos reutiliza `reservas_confirmadas()`, que también reconoce
  entregas antiguas sin confirmación explícita y cuenta cada solicitud una vez.
  En mantenimiento cuenta unidades por su estado actual, sin unir sus trabajos.
- Ingresos del mes suma exclusivamente pagos registrados de renta y mora, desde
  el inicio del mes hasta el inicio del siguiente en America/Santo_Domingo. Excluye
  depósitos y muestra RD$ con dos decimales. Los contadores vacíos muestran 0.
- Las tres pestañas muestran hasta cinco registros, el total real y un acceso al
  listado completo cuando hay más. Mantenimientos muestra trabajos sin fecha de
  cierre, incluidas fechas futuras, y enlaza al registro dentro del historial de
  la unidad. El filtro `?atencion=1` permite consultar todos esos trabajos.
- **Pagos vencidos** sustituye el marcador de facturas. Se aplica el plazo existente
  de cinco días desde la aprobación a solicitudes aprobadas o vencidas, sin salida,
  cuyo pago inicial siga incompleto y tenga saldo. No se inventa vencimiento para
  la mora de equipos entregados. El filtro `?vencidos=1` en presupuestos reutiliza
  el mismo criterio y conserva el filtro al paginar.
- Archivos nuevos: `apps/mantenimiento/consultas.py` comparte los trabajos abiertos;
  `apps/ventas/consultas.py` comparte los presupuestos vencidos;
  `apps/mantenimiento/templates/mantenimiento/mantenimiento_atencion.html` muestra
  el listado completo; `apps/cuentas/tests_dashboard.py` contiene diez pruebas del
  panel, fechas, importes, permisos y destinos de los enlaces.
- Pasaron **143 pruebas** en SQLite temporal, `manage.py check`,
  `makemigrations --check --dry-run` y `git diff --check`. Se cubrieron listas
  vacías, límite de cinco, paginación, mantenimiento sin duplicar unidades,
  alquileres antiguos, cobros parciales, límites inclusivos del plazo y límites
  del mes y año en la zona local, además de excluir depósitos de los ingresos.
  No se requieren migraciones nuevas.
- Comprobación local de solo lectura: 7 disponibles, 2 alquileres activos (#1 y
  Ana #2), 1 pendiente (Carla #4), 0 unidades en mantenimiento y RD$15000.00 de
  ingresos del mes. Los enlaces abren los registros correspondientes y se
  conservaron todos los datos de solicitudes, presupuestos, pagos, reembolsos y
  mantenimientos, incluidas Ana, Luis y Carla.

### Rechazo manual en ventana de confirmación — 13 de noviembre de 2026

- En la lista y el detalle, **Aprobar** conserva la acción principal. A su derecha,
  **Rechazar solicitud** aparece en rojo sólido y abre una ventana con
  el diseño de confirmación existente de Mantenimiento. El motivo solo aparece
  dentro de esa ventana; Cancelar y Cerrar no envían el formulario.
- `apps/alquileres/templates/alquileres/solicitud_rechazo_modal.html` comparte la
  ventana entre ambas pantallas, con título por solicitud, motivo obligatorio,
  aviso de que el cliente lo leerá en Mis alquileres y confirmación explícita.
  Se reutiliza la validación del servidor bajo bloqueo: motivo de hasta 1000
  caracteres y solicitud todavía pendiente. El rechazo por cruces desde el
  presupuesto conserva su flujo.
- `apps/alquileres/tests_rechazo_manual.py` añade seis pruebas con datos ficticios
  en una base temporal: ventanas y controles de cancelación, motivo inválido,
  solicitud revisada mientras la ventana estaba abierta, permisos y rechazo
  confirmado con motivo visible para el cliente sin cambiar su comentario.
- Pasaron **80 pruebas de alquileres y ventas**, incluidas las de rechazo por
  cruces y confirmación concurrente, además de `manage.py check` y
  `git diff --check`. Una comprobación local de solo lectura verificó las
  ventanas de Luis y Carla y conservó todos los campos de las solicitudes #2,
  #3 y #4, sus presupuestos y sus pagos: Ana aprobada; Luis y Carla pendientes.
  No se requieren migraciones para este ajuste.

### Contador de solicitudes por revisar — 13 de noviembre de 2026

- El panel del Administrador calcula `kpis.solicitudes_pendientes` contando las
  solicitudes en estado `Pendiente`. La tarjeta conserva su diseño y usa
  `default_if_none:0` para mostrar el cero en lugar de sustituirlo por un guion.
- Las 5 pruebas de `apps.cuentas` pasaron, incluidas las nuevas comprobaciones
  de la tarjeta con 3 pendientes y sin pendientes en SQLite temporal. Se verificó
  también que el panel local renderiza 3 con una conexión de solo lectura y que
  todos los campos de las solicitudes #2, #3 y #4 permanecieron intactos.

### Inicio del Cliente y confirmación por pago — 13 de noviembre de 2026

- El Cliente dispone de un inicio con alquileres activos y próximo paso, además
  de **Mis alquileres** con historial, presupuesto y estados derivados de revisión,
  renta y depósito inicial, entrega y devolución. Los accesos por URL continúan
  limitados al propietario de la solicitud y del presupuesto.
- Aprobar deja la solicitud **Pendiente de pago**. El pago que completa renta y
  depósito confirma la reserva; el Administrador revisa las solicitudes de la misma
  unidad con períodos cruzados y escribe un motivo para cada rechazo. El servidor
  valida una lista firmada y vuelve a comprobar disponibilidad bajo bloqueo antes
  de guardar pago, confirmación y rechazos en una transacción.
- Los rechazos conservan el comentario original y ofrecen catálogo por categoría
  y una nueva solicitud del mismo equipo con el plan anterior. El calendario
  distingue fechas ocupadas y comprueba el período completo; el servidor revalida
  al enviar. Los reembolsos del depósito no reducen la renta pendiente.
- Los archivos nuevos, las reglas y los pasos de comprobación están descritos en
  [Cliente y confirmación de reservas](docs/flujo-cliente-reservas.md).
- Verificación: **125 pruebas Django aprobadas** en SQLite temporal, incluidas
  conexiones concurrentes, permisos, formularios desactualizados y reversión ante
  fallos; controles JavaScript comprobados con Node.js y DOM mínimo. `check`,
  `makemigrations --check --dry-run` y `git diff --check` sin incidencias. La revisión
  visual quedó pendiente porque el control del navegador no estaba disponible;
  no se comprobó SQL Server en esta sesión.
- Se aplicó `alquileres.0005_confirmacion_reserva_y_motivo` a SQLite local con
  respaldo verificado. También se aplicó `cuentas.0004`, que ya estaba pendiente
  y era necesaria para cargar usuarios. Se conservaron los recuentos: 4 usuarios,
  1 unidad, 1 solicitud, 1 presupuesto, 0 pagos y 0 reembolsos. Los respaldos
  `respaldo_antes_cliente_20261113_205901.sqlite3` y
  `respaldo_antes_cliente_20261113_205939.sqlite3` están excluidos de Git.

### Alertas de devolución atrasada — 11 de noviembre de 2026

- En **Salidas y retornos**, el administrador puede filtrar las maquinarias
  entregadas que aún no han sido devueltas después de su fecha estimada. Una
  alerta y un contador hacen visible el apartado de devoluciones atrasadas.
- En sus solicitudes, el cliente ve qué maquinaria tiene atrasada, la fecha
  estimada de devolución y los días transcurridos desde esa fecha. El atraso
  empieza el día siguiente a la fecha estimada.
- Comprobaciones: `manage.py test apps.alquileres --noinput` (44 pruebas
  aprobadas); `git diff --check` sin errores.

### Catálogo público y detalle de maquinaria — 11 de noviembre de 2026

- Los visitantes pueden abrir los detalles de unidades disponibles desde el
  catálogo sin iniciar sesión. La información pública conserva las tarifas y
  descripción, pero no expone el costo de adquisición; las unidades que no
  están disponibles no se muestran en este acceso público.
- La vista pública del detalle usa el ancho completo, sin la barra lateral del
  panel ni el botón **Cerrar sesión**. Incluye enlaces para volver al inicio e
  iniciar sesión. Los usuarios autenticados mantienen la navegación normal del
  panel.
- El visitante puede elegir **Iniciar sesión para solicitar**. La solicitud
  continúa requiriendo autenticación y, después de ingresar, se respeta el
  destino de solicitud original.
- Comprobaciones: `manage.py test apps.inventario.tests.CatalogoPanelTests`
  (12 pruebas aprobadas, incluyendo vista pública, solicitud e interfaz
  autenticada); `git diff --check` sin errores.

### Tarjeta de perfil por rol — 11 de noviembre de 2026

- La tarjeta del panel muestra las iniciales del nombre y apellido, y el nombre
  completo del usuario. Solo las cuentas Administrador y Técnico muestran su
  rol en la tarjeta; a los Clientes no se les presenta esa etiqueta.
- El formulario de creación de técnicos ahora solicita apellido por separado
  para construir correctamente sus iniciales y nombre. También se corrigió la
  plantilla del perfil, que estaba mostrando literalmente la expresión del
  nombre en vez de evaluarla.
- Comprobaciones: `manage.py test apps.tecnico_mantenimiento.tests.GestionTecnicosTests`
  (7 pruebas aprobadas).

### Gestión de técnicos de mantenimiento — 10 de noviembre de 2026

- Se creó `apps/tecnico_mantenimiento/` para gestionar cuentas técnicas desde el
  panel. Solo administradores pueden crear y consultar técnicos; el formulario
  solicita nombre, correo, teléfono, especialidad y una contraseña definida por
  el administrador. El registro público sigue creando cuentas de Cliente.
- El perfil de usuario incorpora la especialidad técnica mediante
  `apps/cuentas/migrations/0003_usuariopersonalizado_especialidad.py`. El técnico
  accede a un dashboard propio con enlaces a maquinaria y mantenimiento; puede
  consultar estados sin ver el costo de adquisición.
- Se probaron creación y permisos, el rechazo de asignar el rol técnico desde el
  registro público, el dashboard y el cambio de contraseña. Las suites de
  técnicos, cuentas, mantenimiento e inventario aprobaron **25 pruebas**;
  `manage.py check` y `makemigrations --check --dry-run` finalizaron sin errores.
  La migración de especialidad se aplicó a la base SQLite local.

### Configuraciones de cuenta — 10 de noviembre de 2026

- Se creó `apps/configuraciones/` como espacio para opciones de cuenta de
  Administrador, Cliente y Técnico. El enlace **Configuraciones** aparece al
  final del menú del panel para esos roles.
- Por ahora incluye **Cambiar contraseña**: solicita la contraseña actual, la
  nueva y su confirmación. Si la contraseña actual no coincide o la nueva no se
  confirma correctamente, no se guarda; al completar el cambio se muestra un
  mensaje de éxito.
- `apps/configuraciones/tests.py` cubre acceso por rol, autenticación, cambio
  válido y contraseñas incorrectas o no coincidentes. Las suites de
  configuraciones, técnicos y cuentas aprobaron **13 pruebas**; `manage.py check`
  y `makemigrations --check --dry-run` finalizaron sin errores. Esta función no
  requiere migraciones.

### Solicitudes pendientes compartidas — 10 de noviembre de 2026

- Las solicitudes pendientes ya no cambian el estado de la unidad ni la ocultan
  del catálogo; distintos clientes pueden solicitar la misma unidad mientras
  ninguna solicitud haya sido aprobada. Cada cliente consulta únicamente sus
  propias solicitudes y el administrador puede consultar todas.
- Al aprobar una solicitud, la unidad pasa a **Alquilado** y las demás
  solicitudes pendientes para esa unidad se marcan **Rechazada**. La aprobación
  y el rechazo de solicitudes competidoras se realizan en la misma operación.
- `apps/alquileres/migrations/0004_pendientes_no_reservan_unidad.py` libera las
  unidades que quedaron alquiladas por solicitudes pendientes del comportamiento
  anterior, sin cambiar las que tienen una solicitud aprobada activa.
- Se actualizaron las pruebas de integración y concurrencia en
  `apps/alquileres/tests_integracion.py` y
  `apps/alquileres/tests_concurrencia.py`. Comprobaciones: las suites de
  alquileres, ventas, inventario y mantenimiento aprobaron **71 pruebas**;
  `manage.py check` no encontró incidencias y
  `makemigrations --check --dry-run` no detectó cambios. La base de trabajo no
  se modificó.

### Integración local de alquileres, entregas y reportes — 9 de noviembre de 2026

- Se completó el borrador de `feat/integrar-alquileres-entregas-reportes` sobre
  `main` de Aneurys (`176312b`). El trabajo se mantiene en las aplicaciones
  existentes `apps/alquileres/` y `apps/reportes/`.
- Alquileres incorpora filtros administrativos combinables, detalle con fechas y
  responsables, aislamiento de solicitudes por cliente y prevención de duplicados
  pendientes. Conserva los planes diario/semanal/mensual, sus tarifas contratadas
  y la creación transaccional del presupuesto original.
- `apps/alquileres/bloqueos.py` comparte el bloqueo de unidad entre solicitud,
  aprobación, salida, retorno y edición. Usa bloqueo de fila cuando está disponible;
  en SQLite adquiere primero el bloqueo de escritura mediante una actualización
  sin cambio. Si otra operación impide guardar, se informa del error y se revierte
  la operación completa.
- Las nuevas plantillas `solicitud_detalle.html` y `entrega_lista.html` presentan
  detalle, pendientes, devueltas e historial completo. `solicitud_resumen.html` y
  `solicitud_acciones.html` comparten datos y acciones entre pantallas. La bandeja
  se enlaza en `templates/dashboard/base_dashboard.html` para administradores.
- Los movimientos siguen tomando fecha y responsable del servidor y de la sesión;
  no se admiten fechas manuales. Se conserva la lectura acumulada del horómetro y
  la fórmula de mora de Aneurys. La segunda infracción suspende seis meses
  calendario, ajustando al último día del mes cuando sea necesario. Los registros
  con `politica_mora_aplica=False` no cobran mora ni cuentan para la suspensión.
- La protección de unidades con entrega pendiente se aplica también en
  `apps/inventario/models.py`, `forms.py` y `views.py`; el guardado vuelve a validar
  bajo bloqueo para impedir que una edición antigua libere una unidad entregada.
- Los cuatro reportes abren inicialmente con HTTP 200 y permiten consultar sin
  filtros. Pantalla y XLSX comparten las filas filtradas. Salida y retorno se
  exportan como fechas nativas de Excel en hora de Santo Domingo. Se conserva el
  acceso exclusivo a superusuarios activos y la retirada de CSV.
- `apps/alquileres/tests_integracion.py`, `tests_concurrencia.py` y
  `apps/reportes/tests.py` cubren el flujo completo, regresiones y descargas.
  `apps/alquileres/tests_datos.py` contiene datos ficticios compartidos y
  `apps/__init__.py` permite descubrir las pruebas como paquetes. No se requieren
  migraciones nuevas ni se modifican las migraciones históricas.

Comprobaciones locales (SQLite temporal, independiente de la base de trabajo):

```powershell
.\.venv\Scripts\python.exe -B manage.py test --noinput
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
```

Las pruebas de concurrencia usan conexiones separadas. Su resultado corresponde a
SQLite; una futura instalación en SQL Server debe ejecutar allí la misma suite.
Resultado de esta integración: **67 pruebas aprobadas, sin omisiones**, con
Django 6.1.3 y openpyxl 3.1.5. `check` no encontró incidencias y
`makemigrations --check --dry-run` no detectó cambios. No se aplicaron migraciones
ni se crearon registros en la base de trabajo.

### Correcciones del horómetro y los avisos del retorno

- `MaquinariaIntegralForm` compara el horómetro enviado con la lectura actual de
  la unidad, después de releerla bajo bloqueo al guardar. Rechaza valores menores
  tanto al editar como al reactivar, por lo que un formulario abierto antes de un
  retorno no sobrescribe las horas registradas después. Se admiten lecturas
  iguales o superiores; el rechazo revierte también los cambios de catálogo.
- Los avisos de mora, devolución a tiempo y suspensión se publican mediante
  `transaction.on_commit` en `apps/alquileres/views.py`. Si falla el guardado o la
  confirmación de la transacción, se descartan esos avisos y solo se muestra el
  error de la operación.
- Se añadieron seis pruebas de regresión en
  `apps/alquileres/tests_integracion.py`, incluidos fallos al confirmar la
  transacción y al guardar la suspensión. La suite completa aprobó **73 pruebas**
  sobre SQLite temporal. `check` no encontró incidencias y
  `makemigrations --check --dry-run` no detectó cambios. La base de trabajo no se
  modificó.

### Catálogo público

- Se registró la vista pública del catálogo en la ruta `/catalogo/`, que lista
  unidades activas y disponibles y permite buscar, filtrar por categoría y
  ordenar por tarifa. La implementación está en
  `apps/inventario/views.py` y `templates/publico/catalogo.html`.
- Se conectaron el menú, el botón de acceso y los enlaces de categorías de la
  página principal con dicha ruta, en `templates/publico/index.html`.
- Se ajustó el botón para volver a maquinaria en la vista de clientes, de modo
  que facilite regresar a la lista de maquinaria.
- Se añadió en `apps/inventario/tests.py` una prueba de integración para
  comprobar el acceso desde el inicio, la visualización de maquinaria y el
  enlace al detalle.
- Comprobaciones ejecutadas: `manage.py test apps.inventario.tests`
  (10 pruebas aprobadas) y `manage.py check` (sin incidencias).

### Permisos de gestión del inventario

- Los botones **Gestionar Categorías** y **Registrar Maquinaria** solo aparecen
  para administradores en la lista de maquinaria.
- El acceso a listar y crear categorías requiere permiso administrativo también
  desde las rutas directas. El registro de maquinaria conserva su restricción
  administrativa existente.
- Se ampliaron las pruebas en `apps/inventario/tests.py` para verificar que el
  cliente no ve esos botones y recibe HTTP 403 al acceder directamente a las
  rutas de gestión, mientras el administrador conserva el acceso.
- Comprobación ejecutada: `manage.py test
  apps.inventario.tests.PermisosMaquinariaTests --noinput` (5 pruebas aprobadas).

### Estado y disponibilidad de unidades

- Se conservó el cambio de estado de la unidad en el formulario integral de
  maquinaria. El administrador puede cambiarlo; el listado administrativo
  muestra unidades activas en todos sus estados con la etiqueta correspondiente.
- Los clientes solo ven unidades disponibles en inventario y no pueden abrir
  directamente el detalle de una unidad en otro estado. El catálogo público y
  el panel de inicio solo muestran unidades disponibles; la portada pública no
  lista unidades.
- La lista de mantenimiento refleja todos los estados de las unidades activas.
  La opción de registrar mantenimiento solo se muestra para unidades disponibles
  o que ya están en mantenimiento.
- Alquileres impide nuevas solicitudes de unidades alquiladas, en mantenimiento
  o fuera de servicio para clientes y administradores. Se conservan las
  solicitudes existentes y su historial.
- Comprobaciones ejecutadas: **14 pruebas aprobadas** para inventario, alquileres
  y mantenimiento; luego se repitió la prueba de inicio y catálogo con las
  nuevas verificaciones (aprobada). `manage.py check` sin incidencias.

### Reserva al solicitar y vencimiento por falta de pago

- Al enviar la primera solicitud, la unidad pasa inmediatamente a `Alquilado` y
  deja de aparecer en el inventario del cliente, el catálogo público y el panel
  de inicio. Si se rechaza, vuelve a estar disponible cuando no hay otra reserva.
- La migración reserva también las unidades disponibles que ya tenían solicitudes
  pendientes o aprobadas sin entrega al momento de actualizar el sistema.
- Al aprobarla, se inicia un plazo de cinco días calendario para registrar el
  pago inicial completo: renta más depósito. El sistema considera los pagos
  registrados por administración; no tiene cobro directo en línea para el cliente.
- `apps/alquileres/reservas.py` valida el pago, aplica el vencimiento con bloqueo
  transaccional y libera la unidad solo si no existe otra reserva ni una entrega
  física activa. Las solicitudes vencidas conservan su historial con estado
  `Vencida`; una solicitud ya entregada no vence por falta de pago.
- `apps/ventas/management/commands/expirado.py` implementa el comando
  `manage.py expirado`. Para ejecutar manualmente:

  ```powershell
  .\.venv\Scripts\python.exe manage.py expirado
  ```

- Para que el vencimiento ocurra sin esperar a que alguien use la aplicación,
  crea una tarea en el Programador de tareas de Windows que ejecute el comando
  cada hora. En **Programa o script**, indica la ruta absoluta a
  `.venv\Scripts\python.exe`; en **Agregar argumentos**, `manage.py expirado`;
  y en **Iniciar en**, la carpeta raíz del proyecto. La demora máxima normal
  será de una hora después de cumplirse el plazo.
- La migración `apps/alquileres/migrations/0003_estado_solicitud_vencida.py`
  agrega `Vencida` a los estados permitidos. Aplicar con
  `.\.venv\Scripts\python.exe manage.py migrate`.
- La suite de alquileres, ventas/pagos, inventario y mantenimiento aprobó
  **69 pruebas**. `manage.py check` y `makemigrations --check --dry-run` no
  detectaron incidencias ni migraciones pendientes.

### Validación de tarifas de maquinaria

- Se ajustó `MaquinariaIntegralForm` en `apps/inventario/forms.py` para exigir
  un orden estrictamente creciente: la tarifa diaria debe ser menor que la
  semanal, y la semanal menor que la mensual. También se rechazan importes
  iguales; no se exige una proporción específica entre los planes.
- Se actualizaron las pruebas en `apps/inventario/tests.py` para comprobar el
  rechazo de tarifas iguales y el uso de importes estrictamente crecientes.
- Comprobaciones ejecutadas: 3 pruebas específicas aprobadas y
  `manage.py check` (sin incidencias).

### Gestión de clientes

- Se creó la aplicación `apps/clientes/` para que el administrador consulte los
  clientes registrados, filtre por estado activo/inactivo y busque por nombre,
  correo o teléfono. La ruta del listado es `/clientes/`.
- El detalle de cada cliente muestra su información básica y el historial de
  solicitudes de alquiler, incluyendo maquinaria, estado, fechas y datos de
  salida y retorno. Se consultan los modelos existentes de cuentas, inventario
  y alquileres; esta funcionalidad no requiere tablas ni migraciones nuevas.
- Los archivos `apps/clientes/apps.py`, `urls.py` y `views.py` registran la app,
  las rutas y las vistas restringidas a administradores. Las plantillas
  `apps/clientes/templates/clientes/cliente_lista.html` y
  `apps/clientes/templates/clientes/cliente_detalle.html` implementan las
  pantallas; `apps/clientes/tests.py` cubre acceso, filtros e historial.
- Se vinculó la app en `config/settings.py` y `config/urls.py`, y se colocó el
  enlace **Clientes** debajo de **Solicitudes de alquiler** en
  `templates/dashboard/base_dashboard.html`, visible para administradores.
- No se crearon carpetas propias de CSS o JavaScript: las pantallas usan los
  estilos y componentes ya cargados por el panel.
- Comprobaciones ejecutadas: `manage.py test apps.clientes.tests`
  (5 pruebas aprobadas), prueba específica del enlace del panel (aprobada) y
  `manage.py check` (sin incidencias).

### Planes de alquiler, presupuestos y mora

- Se reemplazó la selección de fecha final por fecha de inicio, plan (diario,
  semanal o mensual) y cantidad. La duración se calcula como 1, 7 o 30 días por
  período, respectivamente, y la fecha final es inclusiva. El formulario está
  en `apps/alquileres/templates/alquileres/solicitud_form.html`; la vista
  previa del presupuesto usa
  `apps/ventas/static/ventas/animations/presupuesto.js`.
- Se implementó `apps/ventas/` para conservar en cada presupuesto la tarifa del
  plan elegida al solicitar, el importe de renta y el depósito reembolsable.
  Los costos internos de adquisición no se muestran al cliente. El cliente
  consulta su presupuesto y el administrador tiene una lista de ventas en
  `/ventas/`; las páginas están en `apps/ventas/templates/ventas/`.
- El administrador puede registrar pagos manuales separados por concepto
  (renta, depósito o mora), método y referencia. El sistema calcula lo pagado y
  el saldo, y valida que no se registre más de lo adeudado por concepto.
  Después del retorno de la maquinaria se permiten reembolsos parciales o
  completos, limitados al depósito efectivamente recibido. No se integra una
  pasarela de pago.
- Se añadieron acciones administrativas para registrar salida y retorno de la
  unidad. El warning aparece desde el primer día posterior a la fecha
  programada. La mora se calcula sobre la tarifa diaria equivalente: 10% por
  cada uno de los días 1–3 y 20% por cada día posterior. La segunda devolución
  con más de 3 días de atraso inactiva la cuenta durante 6 meses.
- La cuenta suspendida se reactiva automáticamente al vencer el plazo cuando
  el cliente intenta iniciar sesión o cuando el administrador abre el listado
  de clientes. Las desactivaciones sin fecha de suspensión no se reactivan por
  este mecanismo. El historial de clientes muestra fechas programadas y reales,
  atrasos, warnings, presupuestos y saldos.
- Se añadieron migraciones en `apps/alquileres/migrations/`,
  `apps/cuentas/migrations/` y `apps/ventas/migrations/`. Los registros
  anteriores conservan sus fechas; la migración deriva la cantidad histórica
  desde el período guardado y excluye esos alquileres de la nueva política de
  mora, pues no se conoce qué tarifa contrataron.
- Comprobaciones ejecutadas: migraciones aplicadas a la base local,
  `manage.py check`, `manage.py makemigrations --check --dry-run`, validación
  sintáctica y detección estática del JavaScript, y 18 pruebas de alquileres,
  ventas, cuentas y clientes aprobadas.

Actualización del 30 de octubre de 2026: las migraciones `0008`–`0010`
conservan el trabajo local de roles y solicitudes; `0011` completa la retirada
física de operadores, con respaldo SQL Server verificado antes del borrado.
Ver [cuentas y roles](docs/cuentas-y-roles.md) y
[retirada de operadores](docs/retirada-operadores.md).
HU-05 y HU-06 quedan retiradas, sin redactar todavía sus reemplazos.

Sprint 4, HU-09: la migración `0012_salida_retorno_maquinaria` amplía la solicitud
existente con fechas y responsables de entrega y devolución, sin duplicar tablas
de alquiler. HU-10 reutiliza esos datos y no requiere cambios de esquema ni
migraciones nuevas. Antes de aplicar HU-09 en otra instalación:

```powershell
.\.venv\Scripts\python.exe manage.py respaldar_sqlserver --motivo pre_hu09
.\.venv\Scripts\python.exe manage.py migrate --noinput
```

## Requisitos

- Python 3.12 a 3.14 (este entorno usa Python 3.14).
- SQL Server 2017 o posterior; se probó con SQL Server 2025 Express.
- Microsoft ODBC Driver 18 for SQL Server.
- PowerShell y Git en Windows.

El backend `mssql-django==2.0.0` soporta Django 6.1 y Python 3.14.

## Instalación

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/configurar_desarrollo.py
```

El último comando crea o completa `config.local.json` sin cambiar secretos ya
existentes. Ese archivo está excluido de Git. La configuración de ejemplo usa
autenticación integrada de Windows contra `localhost\SQLEXPRESS` y la base
`AlquilerEquipos`:

```json
"DATABASE": {
  "ENGINE": "mssql",
  "NAME": "AlquilerEquipos",
  "HOST": "localhost\\SQLEXPRESS",
  "PORT": "",
  "USER": "",
  "PASSWORD": "",
  "OPTIONS": {
    "driver": "ODBC Driver 18 for SQL Server",
    "extra_params": "TrustServerCertificate=yes"
  }
}
```

Para autenticación SQL, escribe `USER` y `PASSWORD` solo en
`config.local.json`. También se admiten las variables `DJANGO_DB_ENGINE`,
`DJANGO_DB_NAME`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT`, `DJANGO_DB_USER`,
`DJANGO_DB_PASSWORD`, `DJANGO_DB_DRIVER` y `DJANGO_DB_EXTRA_PARAMS`.

## Preparar SQL Server

Crea una base vacía si todavía no existe:

```sql
CREATE DATABASE [AlquilerEquipos];
```

Antes de cambiar una base existente, ejecuta el inventario de solo lectura:

```powershell
sqlcmd -S ".\SQLEXPRESS" -E -C -i sql\00_inspeccionar_base.sql
```

Haz y verifica una copia desde SQL Server Management Studio o con
`BACKUP DATABASE ... WITH COPY_ONLY, CHECKSUM` y
`RESTORE VERIFYONLY ... WITH CHECKSUM, STOP_ON_ERROR`. No guardes archivos
`.bak` en Git. Después aplica las migraciones. `--fake-initial`
reconoce `Categoria`, `Maquinaria` y `Unidad` si ya venían del script original;
en una base nueva las crea.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --fake-initial
```

Las migraciones de Django son la fuente de verdad para el módulo implementado.
La migración 0011 necesita permisos para inspeccionar todas las definiciones
SQL, crear un respaldo en el directorio de la instancia y verificarlo. Si falla
el respaldo o encuentra dependencias de operadores, se detiene sin borrar la
tabla. Detén las escrituras durante la migración. Consulta el procedimiento
detallado antes de aplicarla en otra instalación.

Los archivos siguientes conservan y corrigen por separado los objetos futuros
del script del compañero:

- `sql/01_completar_esquema_legacy.sql`: crea los objetos omitidos y corrige
  referencias de `Equipo` a `Maquinaria`.
- `sql/02_procedimientos_legacy_corregidos.sql`: procedimientos derivados del
  original con nombres corregidos y `CREATE OR ALTER`.
- `docs/revision-script-original.md`: hallazgos, diferencias y orden correcto.

Los scripts son aditivos. No eliminan ni reemplazan filas. El módulo web actual
no depende de los procedimientos de alquiler.

## Migrar datos locales anteriores

Conserva `db.sqlite3` y `data/maquinaria_provisional.json` como respaldo. Con la
conexión SQL Server activa, ejecuta:

```powershell
.\.venv\Scripts\python.exe manage.py migrar_datos_locales
```

El comando:

- copia usuarios sin recalcular sus contraseñas: conserva exactamente el hash;
- copia grupos, membresías y permisos compatibles, excluyendo Supervisor,
  Operador y los permisos del modelo retirado;
- convierte el JSON en `Categoria`, `Maquinaria` y `Unidad`;
- no actualiza usuarios, códigos o números de serie que ya existan;
- verifica al final que usuarios, hashes, roles y unidades estén presentes;
- se puede repetir sin duplicar datos.

Se pueden indicar rutas distintas con `--sqlite` y `--json`.

## Roles y acceso

Los roles vigentes y los comandos de creación están documentados en
[cuentas y roles](docs/cuentas-y-roles.md). El administrador conserva todas las
funciones de maquinaria y mantenimiento y gestiona las solicitudes de clientes.
También registra salidas, retornos y consulta el historial de entregas. Cliente
y Técnico no tienen acceso a ese flujo, ni mediante direcciones directas.
La sección Reportes también es exclusiva del Administrador, tanto para consultar
como para descargar Excel (.xlsx). El único total monetario es el costo real de los
mantenimientos filtrados; no se calculan ingresos, pagos o importes de alquiler.
Operador y Supervisor no habilitan ningún permiso de negocio.

Las migraciones conservan las cuentas existentes. Una cuenta que solo pertenecía
a Supervisor queda sin rol hasta que el administrador le asigne uno válido;
no se transforma automáticamente en un cliente.

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py crear_cliente luis --nombre "Luis"
.\.venv\Scripts\python.exe manage.py changepassword luis
```

## Comprobar y ejecutar

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test usuarios
.\.venv\Scripts\python.exe manage.py runserver
```

Abre <http://127.0.0.1:8000/login/>. El administrador de Django está en
<http://127.0.0.1:8000/admin/>.

Las pruebas usan una base temporal `test_AlquilerEquipos` en la misma instancia
SQL Server y la eliminan al terminar. La cuenta configurada debe poder crear y
eliminar esa base de prueba.

## HU-02 y HU-03: fabricación y ubicación

El registro de una unidad exige año de fabricación (entero desde 1 hasta el año
actual) y ubicación actual (hasta 200 caracteres, sin aceptar solo espacios).
El año se valida al recibir el formulario y al validar el modelo. La ubicación
también se exige al validar un modelo nuevo, incluido el formulario de Django
Admin. El Administrador registra y consulta; Cliente y Técnico pueden consultar.

Se reutiliza `Unidad.UbicacionActual`. La migración
`usuarios/0004_anio_fabricacion_unidad` añade `Unidad.AnioFabricacion`, nullable
y sin valor predeterminado. No modifica las ubicaciones ni rellena años antiguos.
Ambos campos pertenecen a cada unidad física, ya que un mismo modelo de catálogo
puede tener unidades fabricadas en años distintos y en diferentes ubicaciones.
El detalle muestra ambos datos; el listado muestra la ubicación. Los datos
desconocidos aparecen como «No especificado/a» sin guardar ese texto en la base.

La página de acceso denegado usa un manejador 403 explícito y muestra un botón
para volver al panel. Conserva el estado HTTP 403 con `DEBUG=True` y `False`.

Verificación del 22 de octubre de 2026: 15 pruebas aprobadas en SQL Server,
incluyendo registro y lectura de los valores persistidos, validaciones, campos
en las plantillas, visualización de valores desconocidos y permisos por rol.
`manage.py check` y `makemigrations --check --dry-run` también pasaron.
La migración se aplicó en la base local y se compararon todas las columnas
anteriores, conservando los datos existentes y los valores desconocidos nulos.

## Archivos locales y Git

`.gitignore` excluye `config.local.json`, `.env`, claves, SQLite, `data/`,
respaldos, copias SQL originales, `tmp/`, `output/`, `sprint3_work/`,
`respaldos_locales/`, `evidencias_locales/`, `sql/legacy/`, el entorno virtual
y cachés.
No uses `git add -f` con esos archivos.

La [guía de organización](docs/organizacion-del-proyecto.md) distingue aplicación,
documentos, fuentes, evidencias y respaldos; `output`, `scripts` y `sprint3_work`
permanecen separados. Las utilidades compartidas están documentadas en
[scripts/README.md](scripts/README.md). Para comprobar Django y ejecutar toda
la suite con un nombre de base temporal único:

```powershell
.\.venv\Scripts\python.exe -B scripts/verificar_proyecto.py
```

Antes de compartir cambios:

```powershell
git status --short
git diff --cached --stat
git diff --cached
```

Trabaja en una rama y usa un pull request para no sobrescribir cambios de otras
personas. Repositorio: <https://github.com/giorgioRD/Alquiler_maquinaria>.


## HU-04: actualizar información de maquinaria

El administrador puede abrir **Editar** desde el listado o **Editar maquinaria**
desde el detalle. El formulario carga los datos actuales y valida los mismos
campos obligatorios que el registro. El código de catálogo y el número de serie
pueden conservar sus valores propios, pero no tomar los de otro registro.
Cliente, Técnico y los usuarios sin rol reciben HTTP 403 ante GET y POST de edición.

Los datos del catálogo se comparten entre todas sus unidades. El formulario
advierte este alcance. La serie, ubicación, estado, año y horas de uso pertenecen
solo a la unidad seleccionada. Ambos grupos se guardan en una transacción:
un error revierte también los cambios de catálogo y cualquier categoría creada.

La migración 0005_fechas_modificacion_maquinaria_unidad añade columnas nullable
FechaModificacion a Maquinaria y Unidad. No inventa fechas para registros
existentes. La edición web registra una fecha solo en el objeto cuyos datos
cambian; abrir el formulario o guardar los mismos valores no modifica la fecha.
El detalle muestra ambas fechas en la zona horaria de República Dominicana.
Las fechas corresponden a la edición web HU-04, no a cambios directos por SQL.

Para aplicar esta HU en otra base SQL Server, comprobar primero el destino y
crear y verificar una copia de seguridad. Después ejecutar:

    .\.venv\Scripts\python.exe manage.py showmigrations usuarios --plan
    .\.venv\Scripts\python.exe manage.py sqlmigrate usuarios 0005
    .\.venv\Scripts\python.exe manage.py migrate --noinput
    .\.venv\Scripts\python.exe manage.py test usuarios --noinput
    .\.venv\Scripts\python.exe manage.py runserver

Prueba manual: entrar como administrador, abrir una unidad y editar su ubicación
y una tarifa. Guardar, comprobar el mensaje de éxito y las fechas, y volver a
consultar para verificar la persistencia. Intentar guardar un campo obligatorio
vacío y una serie de otra unidad. Por último, entrar como Cliente o Técnico y comprobar
que la dirección de edición devuelve acceso denegado.

Validación del 26 de octubre de 2026: después de las 26 pruebas iniciales con
SQLite temporal, se aplicó la migración 0005 en `AlquilerEquipos` sobre SQL Server
Express. Antes se creó un backup `COPY_ONLY` con `CHECKSUM` y se comprobó mediante
`RESTORE VERIFYONLY WITH CHECKSUM`. El archivo del servidor es
`C:\Program Files\Microsoft SQL Server\MSSQL17.SQLEXPRESS\MSSQL\Backup\AlquilerEquipos_antes_HU04_0005_20261026T223842Z.bak`.

Se verificaron las dos columnas `FechaModificacion` de tipo `datetimeoffset`,
nullable, y el registro de la migración en `django_migrations`. Se conservaron
los recuentos de 4 catálogos y 4 unidades, todos con fecha de modificación `NULL`.
No quedaron migraciones pendientes. `check` y `makemigrations --check --dry-run`
pasaron sin incidencias.

Las 26 pruebas también pasaron en la base temporal SQL Server
`test_AlquilerEquipos`, aplicando toda la cadena de migraciones y eliminando la
base temporal al terminar. Cubren permisos GET/POST, edición, validaciones,
fechas y reversión de la transacción ante un fallo de guardado. No se encontraron
triggers en las tablas de maquinaria de la base revisada. Esta ejecución no
incluye pruebas de concurrencia entre editores ni una revisión visual en navegador;
la prueba manual descrita arriba queda como comprobación de aceptación.

## HU-05 y HU-06 retiradas

HU-05 (registro y consulta de operadores) y HU-06 (asignación de operadores)
quedan retiradas. No se redactan reemplazos en esta entrega. Las migraciones
históricas se mantienen para las instalaciones existentes; el módulo web y su
tabla SQL se retiran mediante migraciones nuevas. Consulta el
[procedimiento y las evidencias de retirada](docs/retirada-operadores.md).

## HU-07: registrar mantenimiento (Sprint 3)

El registro y la consulta de mantenimiento se conservan con Administrador y
Técnico. HU-05 y HU-06 están retiradas. El documento Word no se modifica.

Técnico y Administrador pueden abrir **Mantenimientos** desde la navegación o
**Registrar mantenimiento** desde el panel. El formulario exige unidad física,
fecha válida, tipo (`Preventivo` o `Correctivo`), descripción de hasta 300
caracteres y costo decimal no negativo, con hasta dos decimales. La selección
muestra código y nombre de catálogo, serie, ID de unidad y estado. La fecha
se introduce en el control de calendario; no se añade una restricción de
fechas pasadas o futuras que la historia no pide.

El técnico responsable se obtiene de la sesión, se muestra en pantalla y se
guarda como relación protegida con el usuario Django; no es un campo editable.
Un POST con otro `tecnico`, `tecnico_id`, estado o fecha de cierre no puede
sobrescribir esos valores. Si un administrador registra la actividad, queda
identificado ese administrador como responsable.

Se reutiliza `Unidad.Estado='Mantenimiento'`, mostrado como **En mantenimiento**.
Se admiten unidades activas con catálogo activo y estado `Disponible` o
`Mantenimiento`; se rechazan `Alquilado`, `Baja` e inactivas. Admitir el estado
`Mantenimiento` permite registrar más actividades sin inventar un cierre.
Al guardar se bloquea y relee la unidad, se valida nuevamente su disponibilidad
y se guardan mantenimiento y estado en una misma transacción. Un fallo revierte
ambas operaciones. El catálogo y las otras unidades del mismo modelo se conservan.
Las fechas `FechaModificacion` de HU-04 siguen correspondiendo a edición web.

El historial en `/unidades/<id>/mantenimientos/` muestra fecha, tipo, descripción,
costo y responsable, ordenados de más reciente a más antiguo. Se abre desde
**Mantenimientos → Ver historial** o desde el detalle de maquinaria. Conserva
acceso a unidades inactivas y registros antiguos sin técnico, que se identifican
como **No registrado (registro anterior)**. Cliente puede consultar maquinaria y
solicitar alquileres; mantenimiento está disponible para Administrador y Técnico.
Las cuentas de los roles retirados se conservan sin asignarles un rol nuevo.

### Migración de mantenimiento

`0007_integrar_mantenimiento` adopta `dbo.Mantenimiento` cuando existe y la
crea únicamente si falta. Conserva `MantenimientoID`, `UnidadID`, `FechaInicio`,
`FechaFin`, `Tipo`, `Descripcion` y `Costo`. Añade `TecnicoResponsableID` nullable
para no inventar responsables anteriores, su clave foránea, la relación con
`Unidad` si falta y restricciones de costo/tipo. También crea el grupo `Técnico`.
Los registros web nuevos siempre exigen descripción y responsable.

La migración comprueba primero columnas, tipos, clave primaria, relaciones y
datos legacy. Si detecta un esquema incompatible, unidades inexistentes, costos
negativos o tipos desconocidos, se detiene para revisión sin borrar ni corregir
filas. No se debe usar `--fake` para ocultar ese problema. La adopción es
irreversible mediante migración hacia atrás para proteger la tabla del negocio.
Los procedimientos legacy de inicio/finalización no son utilizados por esta HU;
`FechaFin` se conserva, pero no se ofrece cierre ni retorno automático a Disponible.

En otra instalación, comprobar el destino, inspeccionar el esquema y crear y
verificar un respaldo de SQL Server. Después ejecutar:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --check
.\.venv\Scripts\python.exe manage.py test usuarios --noinput
```

No es necesario ejecutar de nuevo los scripts SQL legacy ni crear manualmente
otra tabla de mantenimiento. `sqlmigrate` no expande la operación Python de
adopción: revisar también `usuarios/migrations/0007_integrar_mantenimiento.py`.

### Crear o asignar un Técnico y probar

```powershell
.\.venv\Scripts\python.exe manage.py crear_tecnico tecnico1 --nombre "Ana" --apellido "Pérez"
.\.venv\Scripts\python.exe manage.py changepassword tecnico1
.\.venv\Scripts\python.exe manage.py runserver
```

El primer comando crea la cuenta o añade `Técnico` a una cuenta existente.
Conserva contraseña y actividad existentes, retira Cliente y los grupos
retirados y conserva otros grupos; rechaza cuentas con
privilegios administrativos. Una cuenta nueva no puede iniciar sesión hasta
establecer la contraseña. Si una cuenta ya tiene contraseña, se puede omitir
`changepassword`. La cuenta debe estar activa. Desde Django Admin también se
puede asignar el grupo **Técnico**, dejando `is_staff` e `is_superuser` desmarcados.

Entrar en <http://127.0.0.1:8000/login/> como Técnico, abrir **Registrar
mantenimiento**, seleccionar la serie correcta, completar los datos y guardar.
Verificar confirmación, responsable, historial y estado **En mantenimiento**.
Reabrir el historial desde **Mantenimientos** para comprobar persistencia.
Usar una unidad destinada a pruebas si no se desea cambiar un equipo operativo.

### Verificación y evidencias

Los resultados actuales de SQL Server, la ubicación de los respaldos y las
comprobaciones de conservación de datos se registran en
[retirada de operadores](docs/retirada-operadores.md).
[La guía de HU-07](docs/hu07-mantenimiento.md) conserva los antecedentes del
27 de octubre; sus referencias a operadores y Supervisor son históricas.
