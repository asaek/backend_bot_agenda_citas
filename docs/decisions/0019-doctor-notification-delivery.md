# ADR 0019 - Entrega de notificaciones al doctor

## Estado

Aceptada, implementada y verificada. Los cortes de eventos, persistencia,
composicion, entrega e integracion del webhook estan implementados; la evidencia de
ejecucion queda en `docs/verification/2026-09-22-doctor-notifications-webhook.md`.

## Contexto

El chatbot ya puede modificar citas mediante el `ToolExecutor` y enviar mensajes
de texto mediante WhatsApp Cloud API. Uno o varios doctores necesitan recibir un
mensaje por cada cita agendada, modificada o cancelada, con un resumen de la
conversacion. La entrega no debe duplicarse ni convertir en fallida la respuesta
del paciente si la API externa no esta disponible.

## Decision

Reutilizar WhatsApp Cloud API y `WhatsAppClient` como canal inicial. El backend
recibira una lista de numeros en `DOCTOR_WHATSAPP_NUMBERS` y cada evento exitoso de
agenda se convertira en una entrega persistida en SQLite para cada numero antes del
envio. La clave de idempotencia sera la pareja `(event_key, recipient_number)` y
cada entrega tendra su propio estado y registro de error. El cuerpo final incluira
el evento de la cita y el resumen conversacional, y sera igual para todos los
destinatarios configurados.

Los envios se mantendran fuera de `CalendarProvider`. Un fallo para un destinatario
quedara registrado sin impedir los intentos dirigidos a los demas y no afectara la
operacion de agenda ni la respuesta al paciente. No se introducira una cola
distribuida durante este MVP.

La implementacion incremental usa `doctor_notifications` como bandeja local. La
pareja `(event_key, recipient_number)` es unica, y el repositorio reclama de forma
atomica entregas `pending` o `failed` antes de un envio futuro. Los estados, errores,
intentos y `provider_message_id` quedan en SQLite; una entrega `sent` no se vuelve a
intentar por un webhook duplicado.

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
- Los numeros y las credenciales de los doctores permanecen fuera del codigo.
