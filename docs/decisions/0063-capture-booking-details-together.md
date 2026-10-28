# ADR 0063 - Capturar nombre y motivo sin imponer turnos separados

## Estado

Aceptada. Sustituye parcialmente ADR 0023 y ADR 0032 en la exigencia de recibir
el motivo en un turno posterior, y ADR 0045 en impedir recibirlo mientras se aclara
el nombre. Se mantienen sus validaciones y la confirmacion de nombres sospechosos.

## Contexto y decision

Las conversaciones del 28/10/2026 mostraron dos desajustes: el backend guardaba
todo el mensaje como nombre aunque incluyera el motivo, y el LLM podia preguntar
y agradecer datos antes de solicitar `create_appointment`. Al entrar despues al
flujo backend se perdian esas respuestas y se solicitaban otra vez.

La captura de texto separa campos literales con etiquetas como `mi nombre es` y
`el motivo es`, o una clausula de sintoma despues del nombre. Se conservan sus
letras y contenido; se eliminan solo las etiquetas, separadores y espacios sobrantes.
La solicitud pendiente conserva el motivo y su mensaje de origen aunque falte
aceptar el nombre. Al recibir ambos datos, usa la validacion y evaluacion existentes
antes de crear la cita; no agrega otra confirmacion de reserva por texto.

El prompt deriva la captura al backend inmediatamente al conocer el horario.
Como compatibilidad para preguntas que aun salgan del agente, al interceptar la
creacion se recuperan respuestas contiguas del paciente a preguntas de nombre o
motivo realmente enviadas en la misma conversacion, durante diez minutos. Se
detiene en una interrupcion o una respuesta ajena a la captura. Un agradecimiento
no demuestra un nombre; ni `patients.name` anterior ni `reason` del tool call
son evidencia de datos nuevos. No se reconstruye una reserva ni una autorizacion
usando el historial.

## Consecuencias

- Se pregunta solo por los datos faltantes, aunque lleguen juntos o el motivo llegue primero.
- Los candidatos de nombre siguen requiriendo confirmacion; el motivo recibido se conserva.
- El JSON incorpora campos opcionales `reason_text` y `reason_message_id`, sin migracion SQLite.
- Se conserva la entrega idempotente existente: una cita y un aviso al doctor por operacion.
