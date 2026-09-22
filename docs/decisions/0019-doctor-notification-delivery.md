# ADR 0019 - Entrega de notificaciones al doctor

## Estado

Propuesta. Se aceptara cuando el diseno sea implementado y verificado.

## Contexto

El chatbot ya puede modificar citas mediante el `ToolExecutor` y enviar mensajes
de texto mediante WhatsApp Cloud API. El doctor necesita recibir un mensaje por
cada cita agendada, modificada o cancelada, con un resumen de la conversacion. La
entrega no debe duplicarse ni convertir en fallida la respuesta del paciente si la
API externa no esta disponible.

## Decision propuesta

Reutilizar WhatsApp Cloud API y `WhatsAppClient` como canal inicial. Cada evento
exitoso de agenda se convertira en una notificacion persistida en SQLite antes del
envio, con una clave unica de idempotencia, estado de entrega y registro del error.
El cuerpo final incluira el evento de la cita y el resumen conversacional, y se
enviara al numero del doctor configurado por el backend.

Los envios se mantendran fuera de `CalendarProvider`. Un fallo de entrega quedara
registrado y no afectara la operacion de agenda ni la respuesta al paciente. No se
introducira una cola distribuida durante este MVP.

## Alternativas consideradas

- Enviar directamente desde `CalendarProvider`: se rechaza porque mezcla agenda y
  comunicacion y dificulta las pruebas.
- Mantener notificaciones solo en memoria: se rechaza porque se perderian ante un
  reinicio y no permitiria idempotencia.
- Introducir Redis o un worker desde el primer corte: se pospone porque el MVP
  actual usa una sola instalacion SQLite y no necesita procesamiento distribuido.

## Consecuencias

- Se reutiliza la autenticacion y el cliente de WhatsApp existentes.
- SQLite conserva una auditoria local y permite reintentos posteriores.
- La entrega sincrona puede aumentar el trabajo del webhook, por lo que un worker
  sera una evolucion posterior si crece el volumen.
- El numero y las credenciales del doctor permanecen fuera del codigo.
