# ADR 0025 - Validacion minima del motivo de cita

## Estado

Aceptada.

## Contexto

La recoleccion del motivo ya impedia que el LLM inventara un valor, pero consideraba
valido cualquier mensaje no vacio del paciente. Un texto evidentemente ilegible podia
terminar guardado en la cita y en la notificacion al doctor.

## Decision

El backend validara el mensaje del paciente mediante un modulo independiente antes de
ejecutar `create_appointment`. La primera capa sera local y conservadora: normalizara
espacios, rechazara entradas sin letras, demasiado cortas o con patrones evidentes de
ruido, y aceptara texto libre sin exigir una palabra medica concreta.

Cuando la validacion rechace el mensaje, `ConversationService` conservara la
solicitud pendiente, no tocara el calendario y pedira una aclaracion. Cuando lo
acepte, usara el texto normalizado del paciente como `reason`; no lo reemplazara por
una categoria ni por un texto generado por el LLM.

Esta decision no clasifica sintomas, no valida medicamente el contenido y no produce
diagnosticos. Esas capacidades requieren una especificacion posterior.

## Consecuencias

- Un texto evidentemente ilegible no crea citas ni notificaciones.
- El paciente puede corregir el motivo sin repetir el horario.
- Las expresiones validas siguen siendo texto libre y no dependen de una lista cerrada.
- Las reglas locales pueden rechazar ruido obvio, pero no resuelven toda la comprension
  semantica del motivo.
