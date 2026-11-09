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

### Catálogo público

- Se registró la vista pública del catálogo en la ruta `/catalogo/`, que lista
  unidades activas y disponibles y permite buscar, filtrar por categoría y
  ordenar por tarifa. La implementación está en
  `apps/inventario/views.py` y `templates/publico/catalogo.html`.
- Se conectaron el menú, el botón de acceso y los enlaces de categorías de la
  página principal con dicha ruta, en `templates/publico/index.html`.
- Se añadió en `apps/inventario/tests.py` una prueba de integración para
  comprobar el acceso desde el inicio, la visualización de maquinaria y el
  enlace al detalle.
- Comprobaciones ejecutadas: `manage.py test apps.inventario.tests`
  (10 pruebas aprobadas) y `manage.py check` (sin incidencias).

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
