# Cliente y confirmación de reservas

La aprobación permite pagar; la reserva se confirma al completar **ambos** conceptos:
renta contratada y depósito inicial. La mora y los reembolsos se contabilizan por
separado. Un reembolso nunca se aplica como abono a la renta.

## Pantallas y estados

El inicio del Cliente muestra sus solicitudes activas y su próximo paso. **Mis
alquileres** incluye también rechazadas, vencidas y devueltas. Listado, detalle y
presupuesto consultan exclusivamente los datos del cliente autenticado; el
Administrador mantiene acceso global.

Las etiquetas se derivan del estado administrativo, el plazo de cinco días desde
la aprobación, los pagos por concepto, la salida y el retorno: Pendiente de
aprobación, Requiere respuesta, Aplazada, Pendiente de pago, Pendiente de entrega,
En uso, Devuelto, Rechazado, Cancelada y Vencido. Un alquiler entregado conserva
En uso aunque su devolución esté atrasada;
el aviso de atraso sigue mostrándose aparte. El comando `expirado` continúa
persistiendo el vencimiento; la interfaz ya lo reconoce aunque aún no se haya
ejecutado el comando.

Para solicitudes vencidas, el administrador puede usar **Enviar solicitud** para
dejar un aviso en Mis alquileres y enviar un correo al cliente preguntando si
sigue interesado. El cliente puede **Volver a solicitar** con nuevas fechas;
el aviso no crea una solicitud ni garantiza disponibilidad. Solo los clientes
pueden registrar solicitudes de alquiler.

Pendiente de aprobación conserva el amarillo; Pendiente de pago usa azul claro
con texto azul oscuro. Devuelto usa fondo gris carbón `#343A40` y texto blanco,
mientras En uso conserva el verde. Estas etiquetas se comparten entre Solicitudes,
Entregas y el detalle; la pestaña Devueltas mantiene el azul.

En el presupuesto, el formulario de pago muestra los cruces y exige un motivo
individual dirigido al cliente cuando el monto completa el pago inicial. Incluye
solicitudes pendientes y aprobadas cuyo pago inicial aún está incompleto y vigente.
En lugar de rechazarlas, el sistema conserva las solicitudes y guarda el mensaje
del administrador en Mis alquileres; también envía un correo con un saludo cordial
y el motivo. El cliente puede aceptar el aplazamiento o cancelar. Las cancelaciones
con pagos registrados requieren contactar al administrador para revisar el
reembolso.

La confirmación bloquea primero la unidad física, luego la solicitud y el
presupuesto. Revalida disponibilidad y cruces y guarda pago, confirmación y avisos
en una transacción; solo después del commit intenta enviar los correos. Usa el
bloqueo común existente: de fila en los motores que lo soportan y de escritura en
SQLite. Ante contención se informa que no se guardaron cambios y se pide volver a
revisar. Una entrega requiere renta y depósito completos. En **Salidas y retornos**, la
vista Salidas programadas hoy muestra las solicitudes aprobadas cuya renta y
depósito están pagados y cuyo período solicitado incluye la fecha actual. Las
solicitudes con fechas futuras no habilitan una salida anticipada.

Al aceptar el aplazamiento, la solicitud queda en cola hasta el retorno real de la
unidad. Después del retorno se programa una solicitud a la vez, evitando períodos
confirmados y conservando la duración original. El inicio se coloca al menos seis
días después de la devolución para conservar los cinco días habituales de pago;
el pago inicial debe completarse antes de la fecha de inicio. Se notifica la nueva
fecha por correo y en Mis alquileres. Si una aprobación sin pago tenía pagos
parciales y recibe un aviso, puede aplazarla, pero para cancelarla debe contactar
al administrador.

El rechazo manual también exige motivo. Los motivos se guardan en
`motivo_rechazo`; nunca reemplazan `comentario`. Las rechazadas anteriores sin
motivo conservan sus datos y muestran que no se registró un motivo.

En la lista y el detalle, Rechazar solicitud aparece en rojo sólido a la derecha
de Aprobar. Abre la ventana de motivo; Cancelar y Cerrar no envían el formulario.
El detalle del rechazo presenta el motivo en un recuadro ámbar claro y conserva
los accesos azules a otras maquinarias y a fechas disponibles.

**Ver otras maquinarias** abre el catálogo autenticado con la categoría del equipo
y permite limpiar el filtro existente. **Ver fechas disponibles** abre otra
solicitud para la misma unidad y preselecciona plan y cantidad. El calendario
muestra las reservas confirmadas sin datos personales y comprueba todos los días
del plan (7 por semana, 30 por mes). El servidor vuelve a comprobar bajo bloqueo al
enviar; un conflicto conserva el formulario y permite elegir otras fechas.

Las unidades Alquiladas se pueden consultar desde el catálogo autenticado para
solicitar períodos libres. El catálogo público conserva su filtro de Disponible.
Las solicitudes pendientes y las aprobaciones sin pago no ocupan fechas.

## Correo de avisos

El envío usa el backend SMTP de Django. Configura en el `.env` del proyecto
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS` o `EMAIL_USE_SSL`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `DEFAULT_FROM_EMAIL`. No se incluyen
credenciales en el repositorio. Si el servidor SMTP falla, el aviso sigue visible
en Mis alquileres, el error queda registrado y el administrador recibe un mensaje.

## Archivos nuevos

- `templates/dashboard/cliente_index.html`: inicio del Cliente con las tarjetas existentes.
- `apps/alquileres/templates/alquileres/estado_cliente.html` y `proximo_paso.html`:
  etiqueta y orientación compartidas entre tarjetas y presupuesto.
- `apps/alquileres/static/alquileres/disponibilidad.js`: calendario y validación del período.
- `apps/ventas/static/ventas/confirmacion_reserva.js`: revisión de cruces y botón del pago final.
- `apps/alquileres/migrations/0006_remove_solicitudalquiler_ck_solicitud_estado_and_more.py`:
  campos de aviso/aplazamiento y estado de cancelación.
- `apps/alquileres/notificaciones.py`: correo para avisos de indisponibilidad y nuevas fechas.
- `apps/alquileres/tests_flujo_cliente.py`: aceptación y regresiones del flujo.
- `apps/alquileres/tests_controles.cjs`: comprobación aislada de controles JavaScript;
  se ejecuta con Node.js y un DOM mínimo, sin dependencias adicionales.

## Verificación

```powershell
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
git diff --check
```

Validación de esta actualización: **91 pruebas aprobadas** en las aplicaciones de
alquileres y ventas, ejecutadas en SQLite temporal.

La suite cubre Ana y Luis en períodos cruzados y Carla en el siguiente período:
aprobar a Ana no cambia las otras solicitudes; pagar confirma a Ana y conserva el
aviso para Luis; Carla sigue pendiente hasta su propia aprobación y puede abrir su
presupuesto. Comprueba las respuestas de aplazar y cancelar, la cola posterior al
retorno, avisos por correo, vencimientos, permisos por URL y rol, pagos parciales,
preselección del plan,
períodos diarios/semanales/mensuales y disponibilidad que cambia con el formulario
abierto, límites inclusivos, unidades distintas, vencimientos, permisos por URL y
rol, reembolso parcial/completo sin reducir renta, falta o alteración de la firma,
motivos vacíos, lista actualizada, pagos repetidos, fallos de guardado y de commit.
Las pruebas de concurrencia usan conexiones separadas para comprobar que solo una
confirmación ocupa un período cruzado.

Los resultados de esta entrega corresponden a **SQLite temporal**. Debe ejecutarse
la misma suite en SQL Server antes de desplegar allí. El control del navegador no
estuvo disponible en esta sesión; la comprobación de JavaScript no sustituye la
revisión visual en navegador.

En otra instalación, respaldar la base y ejecutar `manage.py migrate --noinput`
antes de iniciar el código actualizado.
