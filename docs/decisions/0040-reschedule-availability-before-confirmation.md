# ADR 0040 - Consultar disponibilidad antes de confirmar una reprogramacion

## Estado

Aceptada.

## Contexto

El flujo de reprogramacion pedia una hora concreta y despues mostraba directamente una
confirmacion. El paciente no podia conocer los horarios libres del dia ni el backend
validaba la eleccion contra una lista ofrecida antes de confirmar.

## Decision

Antes de solicitar confirmacion para reprogramar, `ConversationService` consulta
`check_availability` para el dia de destino y presenta los slots devueltos. La seleccion
se conserva durante 10 minutos junto con la cita y la llamada de origen. Solo un horario
de esa lista puede producir la accion pendiente de confirmacion; el proveedor sigue
validando la disponibilidad cuando se ejecuta la mutacion confirmada.

## Consecuencias

- El paciente puede elegir entre horarios realmente libres del dia de destino.
- Una hora no ofrecida no genera confirmacion ni mutacion.
- La confirmacion sigue vinculada a la cita, llamada y nuevo horario exactos.
- La disponibilidad puede cambiar entre la consulta y la confirmacion; el proveedor
  conserva la validacion final y puede rechazar el cambio si el horario ya no esta libre.
