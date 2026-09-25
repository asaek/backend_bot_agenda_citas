# ADR 0022 - Sincronizacion y listados de Google Calendar

## Estado

Aceptada.

## Contexto

Google devuelve eventos cancelados como tombstones cuando `events.list` usa
`showDeleted=true`. Ademas, la documentacion de Google advierte que
`sendUpdates=none` puede impedir la sincronizacion o provocar la perdida de eventos.
El adaptador estaba exponiendo esas cancelaciones al agente y usando la opcion de
notificacion con mayor riesgo operativo.

## Decision

Las consultas normales de citas usan `showDeleted=false` y filtran defensivamente
eventos con estado `cancelled`; solo las mutaciones confirmadas pueden devolver una
cita cancelada. Crear, reprogramar y cancelar usan `sendUpdates=all`. El adaptador no
agrega asistentes, por lo que esta opcion no envia notificaciones al paciente.

## Consecuencias

- El agente ya no puede presentar tombstones cancelados como citas actuales.
- Las cancelaciones confirmadas por el bot quedan en Google y SQLite, pero no se
  muestran en el listado normal del paciente.
- Si Google cancela un evento por una causa externa, el listado lo omitira en lugar
  de inventar que sigue vigente; la causa externa debe revisarse en Google Calendar.
