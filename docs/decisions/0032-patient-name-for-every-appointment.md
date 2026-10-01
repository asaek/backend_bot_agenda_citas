# ADR 0032 - Solicitud del nombre en cada cita nueva

## Estado

Aceptada.

## Contexto

El flujo anterior solo solicitaba el nombre cuando `patients.name` estaba vacio.
Como el nombre se conserva por numero de WhatsApp, las reservas posteriores pasaban
directamente a preguntar el motivo y no confirmaban el nombre asociado a esa cita.

## Decision

Al iniciar cada solicitud nueva de `create_appointment`, `ConversationService`
preguntara el nombre completo, aunque ya exista un valor en `patients.name`. El
backend normalizara y validara la respuesta, actualizara el nombre del paciente y
despues preguntara el motivo. El estado pendiente conservara el identificador del
mensaje que entrego el nombre para que un reintento no use ese texto como motivo.

El horario y el motivo siguen administrados por el flujo backend. No se agrega el
nombre a `create_appointment`; el alcance tecnico del paciente continua ligado al
numero de WhatsApp y el nombre no se considera una identidad verificada.

Esta decision reemplaza parcialmente ADR 0028: mantiene el orden nombre antes del
motivo, pero elimina la condicion de preguntar el nombre solo cuando no estaba
registrado.

## Consecuencias

- Cada cita nueva requiere un mensaje adicional para confirmar el nombre usado en la
  notificacion al doctor.
- El nombre nuevo reemplaza el valor anterior en `patients.name`.
- Los reintentos del mensaje que entrega el nombre no crean citas ni lo procesan como
  motivo.
- No cambian los contratos de herramientas ni el alcance de identidad por WhatsApp.
