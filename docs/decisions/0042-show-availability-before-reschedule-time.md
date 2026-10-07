# ADR 0042 - Mostrar disponibilidad al solicitar cambiar la hora

## Estado

Aceptada.

## Contexto

Cuando el paciente ya habia identificado una cita y pedia cambiar su hora sin indicar
una hora destino, el LLM preguntaba una hora libre antes de consultar el calendario.
Esto obligaba al paciente a proponer horarios a ciegas y podia fallar si el proveedor
LLM no respondia.

## Decision

Ante una solicitud explicita de cambiar la hora sin una hora destino, `ConversationService`
resuelve la cita desde la lista de agenda que se mostro recientemente, consulta las citas
vigentes del paciente y ofrece los horarios libres del dia de esa cita (o del dia nuevo
si el paciente lo indico). Solo ofrece la disponibilidad directamente cuando la cita
objetivo queda identificada de manera unica. Si hay varias candidatas, pregunta cual cita
quiere modificar antes de consultar disponibilidad.

La seleccion sigue ligada a la cita identificada y requiere confirmacion explicita antes
de modificar el calendario. La validacion final del proveedor permanece intacta.

## Consecuencias

- El paciente ve opciones reales antes de proponer una nueva hora.
- Una cita mencionada de forma ambigua no se modifica ni se asocia arbitrariamente.
- Un fallo del LLM no impide mostrar disponibilidad cuando la cita se puede resolver
  desde el historial persistido.
- Ninguna consulta o seleccion de disponibilidad genera por si sola una mutacion o
  notificacion.
