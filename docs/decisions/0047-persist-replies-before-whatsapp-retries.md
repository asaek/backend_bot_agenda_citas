# ADR 0047 - Preparar respuestas antes de reintentar WhatsApp

## Estado

Aceptada e implementada. Verificacion del incremento en
`specs/018-safe-webhook-retries/`.

## Contexto

Despues de fallos de envio por token vencido, un mensaje antiguo fue procesado
con el historial reciente y reabrio la solicitud de nombre de una cita ya
confirmada. Deducir idempotencia solamente del estado `sent` no protege respuestas
fallidas, solicitudes simultaneas ni interrupciones entre una mutacion y su envio.

## Decision

Separar el turno conversacional del intento de transporte. SQLite conserva una
respuesta preparada unica por mensaje entrante con su snapshot de eventos de
cita, y una auditoria independiente por intento. Se reclama el procesamiento
antes de generar y se prepara el cuerpo final antes de llamar a WhatsApp.

Si existe un turno posterior procesado en la conversacion, el reintento anterior
se marca `superseded` y devuelve HTTP 200 sin tocar la conversacion ni enviar al
paciente. Un reintento vigente carga el mismo cuerpo; no llama al LLM ni a las
herramientas. Las respuestas historicas `failed` se recuperan con los datos que
realmente existen, sin inventar eventos o timestamps de envio.

Los turnos de cada paciente se serializan con un bloqueo asincrono compartido
entre solicitudes del proceso Uvicorn actual, obtenido antes de persistir el
mensaje. Pacientes distintos no comparten ese bloqueo. La reclamacion SQLite
tambien impide iniciar nuevamente un mensaje ya reclamado.

Se conserva como `uncertain` un procesamiento interrumpido o una entrega cuyo
resultado externo puede haberse aceptado antes del error de lectura/escritura.
No se repite automaticamente. Una falla previa a la conexion, de configuracion
o un rechazo HTTP permite un reintento del texto preparado. Esto evita prometer
entrega exactamente una vez frente a una API externa sin una clave de envio
idempotente.

## Alternativas

- Regenerar respuestas fallidas: descartada porque repite decisiones y efectos
  usando un contexto distinto.
- Conservar solamente un bloqueo en memoria: insuficiente para recuperar el
  cuerpo preparado o auditar reintentos despues de reiniciar.
- Redis, colas o un worker distribuido: pospuestos; el runtime del MVP es un
  unico proceso y ya utiliza SQLite.

## Consecuencias

- Se agregan tablas de forma aditiva; no se reemplazan mensajes ni citas existentes.
- `messages.created_at` sigue siendo la fecha de creacion del registro. Las
  fechas reales de cada nuevo intento viven en `reply_delivery_attempts`.
- La entrega al doctor recupera los eventos guardados sin repetir la mutacion.
  Si se interrumpe despues de enviar al paciente, el duplicado puede completar
  esa entrega sin reenviar la respuesta del paciente.
- Multiples workers necesitan una exclusion compartida por paciente antes de
  ampliar el despliegue; la exclusion asincrona actual pertenece al runtime de
  un proceso especificado.
