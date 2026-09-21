# ADR 0016 - Identidad local y sincronizacion de citas

## Estado

Aceptada.

## Contexto

Google Calendar es la fuente de verdad, pero sus IDs no deben ser la identidad que
recibe el flujo conversacional. Se necesita conservar una relacion estable entre una
cita del backend y su evento externo, junto con el paciente y la ultima
sincronizacion observada.

## Decision

Agregar la tabla SQLite `appointments` con un `id` entero autoincremental y una
restriccion unica sobre `(calendar_id, google_event_id)`. El repositorio conservara
estado, fechas, motivo, paciente y timestamps UTC. `PersistentCalendarProvider`
traducira el ID interno de las herramientas al ID Google antes de las operaciones de
modificacion y actualizara la fila despues de cada operacion exitosa.

El estado local es un indice sincronizado, no una fuente de verdad alternativa.
Google sigue determinando disponibilidad y estado de sus eventos.

## Consecuencias

- Las herramientas no dependen de IDs Google ni de detalles del proveedor.
- Cancelar conserva el registro y permite auditoria local basica.
- La lista puede reconstruir el mapeo de eventos administrados por el chatbot despues
  de un reinicio.
- Un evento externo borrado o modificado fuera del chatbot requiere una futura
  reconciliacion explicita.
- El fake continúa sin persistencia para mantener las pruebas unitarias simples.
