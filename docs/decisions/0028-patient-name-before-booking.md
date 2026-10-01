# ADR 0028 - Nombre del paciente antes de agendar

## Estado

Reemplazada en parte por ADR 0032. La recoleccion de nombre descrita aqui ahora se
realiza en cada cita nueva, incluso cuando ya hay un nombre registrado.

## Contexto

El flujo de creacion ya solicita el motivo de la consulta, pero un paciente nuevo
puede llegar a la agenda sin un nombre util para la notificacion al doctor. La tabla
`patients` ya dispone de un campo `name`, aunque el flujo conversacional no lo
recolectaba.

## Decision

Cuando una solicitud de `create_appointment` llegue para un paciente sin nombre
registrado, `ConversationService` preguntara primero el nombre completo. El backend
normalizara espacios, guardara el resultado en `patients.name` y luego preguntara el
motivo. El horario continuara en `pending_appointment_reason` durante ambos pasos.

El estado tambien conservara el ID del mensaje que entrego el nombre. Si WhatsApp
reintenta ese mismo mensaje, se repetira la pregunta por el motivo y no se intentara
crear la cita con el nombre como motivo.

No se agrega el nombre a `create_appointment`: es un dato de identidad administrado
por el backend, mientras que la herramienta continua recibiendo solamente el motivo
expresado por el paciente.

## Consecuencias

- Las citas nuevas pueden requerir un mensaje adicional antes del motivo.
- El nombre queda disponible para las notificaciones internas al doctor.
- Antes de ADR 0032, los pacientes con nombre ya registrado conservaban el flujo de
  solicitar solo el motivo.
- El nombre no se considera una identidad verificada durante el MVP tecnico.
