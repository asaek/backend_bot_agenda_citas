# ADR 0015 - Adaptador REST de Google Calendar

## Estado

Aceptada.

## Contexto

El contrato `CalendarProvider` y el ciclo de herramientas ya funcionan con un fake
determinista. El siguiente proveedor debe consultar calendarios existentes, soportar
OAuth o cuenta de servicio, conservar el alcance del paciente y poder probarse sin
credenciales ni red real.

## Decision

Implementar `GoogleCalendarProvider` con `httpx` contra la API REST v3 y usar
`google-auth` exclusivamente para obtener y refrescar tokens. El proveedor recibira
una lista explicita de calendarios y los consultara mediante `freeBusy`; las citas
administradas por el sistema se identificaran con propiedades privadas
`managed_by`, `patient_id` y `conversation_id`.

`CALENDAR_PROVIDER=fake` seguira siendo el valor por defecto. La seleccion explicita
`CALENDAR_PROVIDER=google` cargara la configuracion desde variables de entorno y
secretos montados fuera del repositorio. El `PatientScope` siempre vendra del
backend y se conservara al traducir eventos.

## Consecuencias

- Las pruebas pueden inyectar `httpx.MockTransport` y `StaticAccessTokenProvider`.
- No se introduce el cliente completo de Google, reduciendo la superficie del
  adaptador al contrato de la aplicacion.
- Google limita `freeBusy` a 50 calendarios, por lo que la configuracion rechaza
  listas mayores.
- La reserva hace una consulta de disponibilidad antes de crear el evento, pero la
  coordinacion transaccional entre procesos sigue fuera del MVP.
- Los eventos existentes sin metadatos del sistema no se interpretan ni modifican.

## Referencias

- https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- https://developers.google.com/workspace/calendar/api/v3/reference/events/list
- https://developers.google.com/workspace/calendar/api/guides/extended-properties
- https://developers.google.com/workspace/calendar/api/guides/pagination
