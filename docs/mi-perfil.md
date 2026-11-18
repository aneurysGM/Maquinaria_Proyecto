# Configuraciones → Mi perfil

Administrador, Cliente y Técnico consultan y editan los datos de su propia
cuenta. Los clientes existentes y nuevos no necesitan aprobación del
administrador. El antiguo campo `AutorizacionCliente.puede_editar_perfil`
permanece por compatibilidad y no condiciona este flujo.

Configuraciones muestra únicamente la tarjeta **Mi perfil**. Dentro del perfil:

- Datos personales: nombre, apellido, teléfono y **Guardar datos**.
- Cuenta: correo activo, rol, **Cambiar correo** y **Cambiar contraseña**.
- Técnico: especialidad y disponibilidad en consulta; las gestiona el Administrador.

## Cambio de correo inmediato

En **Mi perfil → Cuenta → Cambiar correo** se introducen el correo nuevo y la
contraseña actual del sistema de alquiler. Al pulsar **Guardar correo**:

1. El servidor obtiene la cuenta del usuario autenticado, comprueba su estado y
   rol y verifica su contraseña actual.
2. Valida el formato y la longitud del correo, lo normaliza a minúsculas y
   comprueba que sea diferente del actual y que no esté registrado, sin
   distinguir mayúsculas y minúsculas.
3. Guarda inmediatamente solo el campo `email`, dentro de una transacción.
   Una colisión de unicidad al guardar muestra un error y conserva el correo anterior.

Desde ese momento se inicia sesión con el correo nuevo y la misma contraseña.
Se conservan ID, rol, nombre, historial y sesión actual. Una contraseña
incorrecta, un correo inválido/duplicado o una cuenta no autorizada no permiten
guardar. Los IDs o campos adicionales enviados por POST no permiten modificar
otra cuenta ni cambiar rol, contraseña o campos técnicos.

Este flujo no envía mensajes, no crea solicitudes pendientes y no requiere
SMTP ni acceso a una bandeja. Los avisos de otros módulos conservan su
configuración de correo en `.env`.

Se retiraron la vista y ruta de confirmación, el servicio de envío y tokens,
las dos plantillas de confirmación y `CAMBIO_CORREO_VIGENCIA_SEGUNDOS`.
Los enlaces emitidos por la versión anterior ya no tienen una ruta válida y
no pueden cambiar cuentas.

## Contraseña y migraciones

Se conserva el formulario actual de **Cambiar contraseña**, incluida la
contraseña anterior y la confirmación de la nueva. El Técnico con primer inicio
pendiente sigue obligado a cambiar su contraseña temporal antes de acceder.

La corrección no agrega ni reescribe migraciones. Se conservan el modelo
`SolicitudCambioCorreo`, su tabla y la migración ya publicada
`cuentas.0006_solicitud_cambio_correo`. Sus registros históricos permanecen
sin uso en Mi perfil. No se eliminan datos existentes.

## Probar en local

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --plan
.\.venv\Scripts\python.exe manage.py runserver
```

Iniciar sesión y abrir:

`http://127.0.0.1:8000/configuraciones/mi-perfil/correo/`

1. Introducir un correo libre y la contraseña actual. Verificar el mensaje de
   éxito y el nuevo correo en Mi perfil inmediatamente después de guardar.
2. Cerrar sesión y entrar con el correo nuevo y la misma contraseña. El correo
   anterior deja de permitir acceso a esa cuenta.
3. Repetir con Administrador, Cliente y Técnico, usando cuentas de prueba.
4. Comprobar que una contraseña incorrecta, un correo duplicado (también con
   mayúsculas) y una dirección inválida muestran errores y conservan el correo activo.

Las pruebas que modifican datos se ejecutan en la base temporal de Django. Las
suites locales de Configuraciones cubren los tres roles, acceso con el nuevo
correo, sesión e identidad conservadas, ausencia de envíos, validaciones, CSRF,
rechazo de cuentas ajenas e inactivas y desactivación de los enlaces anteriores.
También se verifica el registro de un cliente nuevo y la conservación de su
historial al realizar después un cierre mensual.

```powershell
.\.venv\Scripts\python.exe manage.py test test.django.configuraciones test.django.tecnico_mantenimiento test.django.clientes test.django.mantenimiento --noinput
```

Por la política existente del repositorio, las pruebas de desarrollo están en
`test/`, excluido de Git. SQLite, sus respaldos y `.env` también quedan fuera
del control de versiones.
