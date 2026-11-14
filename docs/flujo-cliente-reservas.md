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
aprobación, Pendiente de pago, Pendiente de entrega, En uso, Devuelto, Rechazado y
Vencido. Un alquiler entregado conserva En uso aunque su devolución esté atrasada;
el aviso de atraso sigue mostrándose aparte. El comando `expirado` continúa
persistiendo el vencimiento; la interfaz ya lo reconoce aunque aún no se haya
ejecutado el comando.

Pendiente de aprobación conserva el amarillo; Pendiente de pago usa azul claro
con texto azul oscuro. Devuelto usa fondo gris carbón `#343A40` y texto blanco,
mientras En uso conserva el verde. Estas etiquetas se comparten entre Solicitudes,
Entregas y el detalle; la pestaña Devueltas mantiene el azul.

En el presupuesto, el formulario de pago muestra los cruces y exige un motivo
individual cuando el monto completa el pago inicial. Incluye solicitudes
pendientes de revisión y aprobadas cuyo pago inicial aún está incompleto y
vigente. Las solicitudes vencidas y las de otras unidades o períodos se conservan.
La lista se firma con su unidad, fechas y estados; si cambió, el pago no se guarda
y el formulario vuelve a presentar la lista actual para revisión.

La confirmación bloquea primero la unidad física, luego la solicitud y el
presupuesto. Revalida disponibilidad y cruces y guarda pago, confirmación y motivos
en una transacción. Usa el bloqueo común existente: de fila en los motores que lo
soportan y de escritura en SQLite. Ante contención se informa que no se guardaron
cambios y se pide volver a revisar. Una entrega requiere renta y depósito completos.

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

## Archivos nuevos

- `templates/dashboard/cliente_index.html`: inicio del Cliente con las tarjetas existentes.
- `apps/alquileres/templates/alquileres/estado_cliente.html` y `proximo_paso.html`:
  etiqueta y orientación compartidas entre tarjetas y presupuesto.
- `apps/alquileres/static/alquileres/disponibilidad.js`: calendario y validación del período.
- `apps/ventas/static/ventas/confirmacion_reserva.js`: revisión de cruces y botón del pago final.
- `apps/alquileres/migrations/0005_confirmacion_reserva_y_motivo.py`: campos nuevos,
  sin modificar solicitudes históricas ni inventar motivos o fechas de confirmación.
- `apps/alquileres/tests_flujo_cliente.py`: aceptación y regresiones del flujo.
- `apps/alquileres/tests_controles.cjs`: comprobación aislada de controles JavaScript;
  se ejecuta con Node.js y un DOM mínimo, sin dependencias adicionales.

## Verificación

```powershell
.\.venv\Scripts\python.exe -B manage.py test --noinput
.\.venv\Scripts\python.exe -B manage.py check
.\.venv\Scripts\python.exe -B manage.py makemigrations --check --dry-run
node apps/alquileres/tests_controles.cjs
node apps/alquileres/tests_sugerencias_controles.cjs
git diff --check
```

Última ejecución de la suite Django: **150 pruebas aprobadas en SQLite temporal**.

La suite cubre Ana y Luis en períodos cruzados y Carla en el siguiente período:
aprobar a Ana no cambia las otras solicitudes; pagar confirma a Ana y rechaza a
Luis con motivo; Carla sigue pendiente hasta su propia aprobación y puede abrir
su presupuesto. Comprueba ambos destinos del rechazo, preselección del plan,
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
