# ADR 0024 - Disponibilidad antes de elegir la hora

## Estado

Aceptada.

## Contexto

Cuando el paciente solicita una cita para un dia pero no indica una hora, el LLM
puede pedir una hora exacta en lugar de consultar los espacios libres. Esa respuesta
obliga al paciente a adivinar horarios y no aprovecha `check_availability`.

## Decision

`ConversationService` detectara solicitudes reconocibles de agenda sin hora exacta
para `hoy`, `manana`, `pasado manana` o un dia de la semana. El backend consultara
`check_availability` para todo ese dia, eliminara horarios duplicados entre
calendarios y mostrara los espacios libres antes de invocar al LLM.

Las solicitudes que ya contienen una hora exacta continuaran por el flujo normal de
creacion, incluida la pregunta obligatoria por el motivo. Las expresiones de fecha
que el detector no reconozca continuaran en el flujo del LLM.

## Consecuencias

- El paciente recibe horarios reales antes de escoger uno.
- Una consulta de disponibilidad no crea una cita ni pregunta aun el motivo.
- La agenda y el horario laboral siguen siendo autoridad del `ToolExecutor`.
- El detector no intenta interpretar fechas arbitrarias ni lenguaje clinico.
