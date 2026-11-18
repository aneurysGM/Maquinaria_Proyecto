# Configuraciones → Mi perfil

Entrega local del 17/11/2026 en `feature/asignar-tecnico`. La rama comenzó limpia,
en `b16b790`, sin diferencias con su referencia local `origin/feature/asignar-tecnico`.
No se hizo fetch, commit ni push.

## Comportamiento

- Administrador, Cliente y Técnico consultan nombre, apellido, teléfono, correo y rol.
- Administrador, Cliente y Técnico editan su propio nombre, apellido y teléfono
  y solicitan cambios de correo. Los clientes existentes y nuevos no necesitan
  aprobación del administrador, tengan o no un registro de autorización.
- `AutorizacionCliente.puede_editar_perfil` se conserva en la base por
  compatibilidad, pero no se consulta al guardar datos, solicitar el cambio de
  correo o confirmarlo. El detalle del cliente ya no muestra ni permite modificar
  ese control. No se necesita una migración de datos ni habilitar cuentas.
- Configuraciones muestra únicamente la tarjeta **Mi perfil**. En **Mi perfil →
  Cuenta** permanecen **Cambiar correo** y **Cambiar contraseña**.
- El Técnico consulta especialidad y disponibilidad; el perfil no permite
  modificarlas ni cambiar rol, contraseña, ID de usuario o correo por POST.
- Se conserva el cambio de contraseña y su flujo de primer inicio de sesión.

## Cambio de correo

En **Mi perfil → Cambiar correo** se introducen el correo nuevo y la contraseña
actual. Se rechazan direcciones inválidas, el correo actual, direcciones ya
registradas (sin distinguir mayúsculas) y contraseñas incorrectas.

La solicitud envía un mensaje únicamente al correo nuevo. El correo anterior
sigue siendo el de acceso hasta confirmar. La base guarda un hash SHA-256 del
token aleatorio, su vencimiento y su estado; no guarda el token en claro ni la
contraseña introducida. El vencimiento predeterminado es de una hora.

El enlace abre una pantalla con **Confirmar cambio de correo**. Solo ese POST,
protegido por CSRF, aplica el cambio. Así, abrirlo o una inspección automática
del correo no consume el enlace. Puede confirmarse sin sesión; si hay sesión
de otra cuenta, se rechaza y se indica que hay que cerrarla primero.

Al confirmar se consultan otra vez la cuenta activa y su rol, la disponibilidad
del correo, el vencimiento y el estado del enlace. Se actualiza exclusivamente
`email` en el mismo usuario y se marca el enlace como utilizado en una transacción.
Se conservan ID, rol, historial, contraseña y la sesión actual. Los errores se
explican en pantalla y conservan el correo activo.

Una nueva solicitud enviada correctamente reemplaza los enlaces anteriores.
Un fallo de SMTP revierte la solicitud nueva y conserva tanto el correo activo
como el enlace pendiente anterior.

## Migración y base local

Nueva migración: `apps/cuentas/migrations/0006_solicitud_cambio_correo.py`.
Crea únicamente la tabla `SolicitudCambioCorreo`. El campo histórico de permiso
de cliente ya existía en la migración inicial; permanece sin condicionar el
perfil. Los dos ajustes posteriores no añaden ninguna migración.

Ya se aplicó en esta base local, después de crear
`respaldo_antes_mi_perfil_20261117.sqlite3`. No se alteraron permanentemente las
cuentas, sus contraseñas, sus permisos ni sus alquileres durante las pruebas.

En otra copia del proyecto, aplicar antes de arrancar:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py runserver
```

Entrar con la cuenta habitual y abrir:

`http://127.0.0.1:8000/configuraciones/mi-perfil/`

También está disponible desde el menú **Configuraciones → Mi perfil**.
Luis y los demás clientes pueden editar sus datos y cambiar su correo desde
ese momento, sin ajustes del Administrador. **Mi perfil → Cuenta → Cambiar
contraseña** abre el formulario existente. El Técnico con primer inicio pendiente
sigue pasando obligatoriamente por ese formulario antes de acceder al sistema.

## Envío real pendiente: ajustes necesarios

En la configuración local se encontró backend SMTP, host `localhost`, puerto 25,
sin TLS/SSL ni usuario o contraseña SMTP. No se realizó ningún envío real ni se
introdujeron credenciales del usuario. Hay que completar `.env` con los datos
del proveedor de correo y reiniciar Django. `.env.example` enumera los ajustes:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=<servidor SMTP del proveedor>
EMAIL_PORT=<puerto del proveedor>
EMAIL_USE_TLS=<True o False según el proveedor>
EMAIL_USE_SSL=<True o False según el proveedor>
EMAIL_HOST_USER=<usuario SMTP>
EMAIL_HOST_PASSWORD=<credencial SMTP o contraseña de aplicación>
DEFAULT_FROM_EMAIL=<remitente autorizado>
EMAIL_TIMEOUT=10
CAMBIO_CORREO_VIGENCIA_SEGUNDOS=3600
```

Usar TLS o SSL según el proveedor; no activar ambos a la vez. Las credenciales
SMTP son para que Django envíe el mensaje; la contraseña actual que pide la
pantalla es la de la cuenta del sistema. No poner secretos en el repositorio.

### Una sola prueba real, a cargo del usuario

1. Con SMTP configurado y Django reiniciado, iniciar sesión como Administrador.
2. Abrir **Mi perfil → Cambiar correo**. El usuario introduce personalmente una
   dirección suya libre y la contraseña actual. Pulsar **Enviar enlace de confirmación** una sola vez.
3. Antes de confirmar, cerrar sesión y comprobar que se puede entrar con el
   correo anterior y la misma contraseña. La cuenta todavía debe mostrar ese
   correo en Mi perfil.
4. Abrir el mensaje desde la bandeja de la dirección nueva y pulsar **Confirmar
   cambio de correo**. El enlace debe abrirse en el mismo equipo que ejecuta
   Django si utiliza `127.0.0.1` o `localhost`.
5. Cerrar sesión y comprobar el acceso con el correo nuevo y la misma contraseña.
   El correo anterior debe fallar para esa cuenta. Verificar el mismo rol e historial.
6. Volver a abrir el mismo enlace: debe explicar que ya se usó, sin modificar el correo.

## Verificación realizada

- **52 pruebas aprobadas** de configuraciones, clientes y técnicos; incluyen
  **26 pruebas de perfil y cambio de correo**, actualizadas a la edición libre
  del Cliente, y el acceso al formulario de contraseña desde Mi perfil.
- **36 comprobaciones aprobadas con las cuentas locales existentes** de Luis
  (ID 6), Técnico (ID 8) y Administrador. Se utilizaron datos ficticios,
  contraseñas temporales exclusivamente dentro de una transacción y el backend
  de correo en memoria. Al terminar, un rollback restauró todos los datos y se
  compararon los usuarios y las autorizaciones con sus valores originales.
- Luis: edición, solicitud y confirmación del correo con la bandera heredada
  desactivada, sin intervención del Administrador. La suite también cubre los
  clientes nuevos sin registro de autorización y la edición exclusiva de la
  cuenta del usuario autenticado.
- Configuraciones: solo tarjeta Mi perfil; dentro del perfil se conservan los
  dos enlaces de cuenta. Cambiar contraseña abre el formulario actual. La suite
  del Técnico confirma que sigue obligatorio en el primer inicio de sesión.
- Luis y Técnico: acceso anterior mientras pendiente, nuevo correo sin acceso
  antes de confirmar, confirmación sin pérdida de historial/rol/contraseña,
  nuevo acceso y rechazo del correo anterior y del enlace ya usado.
- Duplicados (incluidas mayúsculas), contraseña incorrecta, correo ocupado
  después de solicitarlo, enlace vencido/inválido/reemplazado, cuenta inactiva,
  sesión de otro usuario, CSRF, campos no autorizados, fallo SMTP y colisión al
  guardar: cubiertos por la suite.
- `manage.py check`, `makemigrations --check --dry-run` y `git diff --check`: correctos.

En la verificación anterior, al incluir las pruebas de cuentas se ejecutaron
**66 pruebas: 63 correctas y 3 fallos preexistentes**. Se verificó contra un archivo temporal del HEAD original
que fallan las mismas tres comprobaciones de HTML del dashboard:

- `DashboardPendientesTests.test_cuenta_todas_las_pendientes_y_excluye_otros_estados`
- `DashboardPendientesTests.test_sin_pendientes_la_tarjeta_muestra_cero`
- `DashboardAdministradorTests.test_ceros_y_listas_vacias`

Las comprobaciones esperaban la clase `kpi-num` del diseño anterior. No se
modificó el dashboard ni esas pruebas durante esta entrega.

La conexión de control del navegador no estuvo disponible (`browser access host
is unavailable`). Las plantillas se renderizaron mediante Django en las pruebas;
queda pendiente la inspección visual interactiva y la entrega real del mensaje.
Las pruebas se ejecutaron en SQLite; no se validó SQL Server.

Se detectó además un par de cuentas existentes cuyos correos coinciden al
ignorar mayúsculas. Se conservaron intactas. La nueva funcionalidad no permite
elegir ninguna dirección ocupada, incluidas variantes de mayúsculas.

### Repetir las pruebas

```powershell
.\.venv\Scripts\python.exe manage.py test test.django.configuraciones test.django.clientes test.django.tecnico_mantenimiento --noinput
.\.venv\Scripts\python.exe manage.py shell -c "exec(open('test/evidencias/verificar_perfil_local.py', encoding='utf-8').read())"
.\.venv\Scripts\python.exe test/evidencias/verificar_base_rama.py
```

Los archivos de pruebas y evidencias permanecen en `test/`, que ya estaba
excluido de Git por la política existente de esta rama. No se cambió `.gitignore`.

## Archivos tocados

Código, plantillas y configuración:

- `.env.example`
- `config/settings.py`
- `apps/cuentas/models.py`
- `apps/cuentas/migrations/0006_solicitud_cambio_correo.py` (nuevo)
- `apps/configuraciones/forms.py`
- `apps/configuraciones/views.py`
- `apps/configuraciones/urls.py`
- `apps/configuraciones/correo.py` (nuevo)
- `apps/configuraciones/templates/configuraciones/indice.html`
- `apps/configuraciones/templates/configuraciones/mi_perfil.html` (nuevo)
- `apps/configuraciones/templates/configuraciones/cambiar_correo.html` (nuevo)
- `apps/configuraciones/templates/configuraciones/confirmar_correo.html` (nuevo)
- `apps/configuraciones/templates/configuraciones/correo_confirmacion.txt` (nuevo)
- `docs/mi-perfil.md` (nuevo, esta guía)

Pruebas y evidencias locales nuevas, excluidas de Git:

- `test/django/configuraciones/tests_perfil.py`
- `test/django/configuraciones/tests.py` (actualizado)
- `test/evidencias/verificar_perfil_local.py`
- `test/evidencias/verificar_base_rama.py`
- `test/evidencias/perfil_baseline.log`

Base local: `db.sqlite3` (migración aplicada) y
`respaldo_antes_mi_perfil_20261117.sqlite3` (respaldo nuevo), ambos excluidos de Git.

El formulario de permiso y los cambios de gestión en `apps/clientes/views.py`
de la primera versión se retiraron. En `cliente_detalle.html` se eliminó su
sección; respecto de HEAD solo queda un salto de línea final. No se integró main.
