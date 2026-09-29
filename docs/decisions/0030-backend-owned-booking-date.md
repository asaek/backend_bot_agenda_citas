# ADR 0030 - Continuacion de fecha de reserva controlada por el backend

## Estado

Aceptada.

## Contexto

Cuando un paciente expresaba que queria agendar sin indicar un dia, el LLM preguntaba
la fecha, pero el backend no guardaba que la respuesta siguiente debia continuar esa
reserva. Una respuesta corta como `hoy` volvia a depender del LLM y podia terminar en
la respuesta generica de error sin consultar disponibilidad.

## Decision

`ConversationService` detectara una intencion reconocible de agendar sin dia ni hora
exacta, guardara un estado `pending_appointment_date` en `conversations.context_json`
por 10 minutos y preguntara el dia con una respuesta fija. La respuesta relativa se
resolvera con el reloj y la zona horaria de la agenda y consultara `check_availability`
directamente.

La consulta determinista de disponibilidad y la seleccion posterior de un horario no
requieren una llamada al LLM. Los mensajes que no coincidan con el parser admitido
mantienen el estado pendiente hasta que se venza o llegue una fecha reconocible.

## Consecuencias

- Una falla temporal del proveedor LLM no interrumpe la continuacion habitual de esta
  reserva de varios turnos.
- El estado sobrevive reinicios mediante SQLite y expira a los 10 minutos.
- El parser reutiliza las expresiones relativas y los dias de semana ya reconocidos por
  la disponibilidad determinista.
- Las fechas arbitrarias y las solicitudes que ya indican una hora exacta conservan el
  flujo conversacional existente.
