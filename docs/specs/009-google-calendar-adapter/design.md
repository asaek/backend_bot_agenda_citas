# Diseno - Adaptador de Google Calendar

## Composicion

```text
main.py
    |
    +-- CALENDAR_PROVIDER=fake   -> FakeCalendarProvider
    |
    +-- CALENDAR_PROVIDER=google -> GoogleCalendarProvider
                                      |
                                      +-- AccessTokenProvider
                                      |     +-- OAuth google-auth
                                      |     +-- Service account google-auth
                                      |
                                      +-- httpx REST client
```

`GoogleCalendarProvider` implementa exclusivamente `CalendarProvider`. `ToolExecutor`
mantiene la validacion de argumentos, horario laboral, conflictos visibles y alcance
del paciente antes y despues de la llamada al proveedor.

## Autenticacion

`GoogleAuthTokenProvider` adapta `google-auth` y refresca credenciales de forma
asincrona mediante `asyncio.to_thread`. OAuth acepta un access token para pruebas o
un refresh token para ejecucion prolongada. Las cuentas de servicio se cargan desde
un archivo externo y pueden usar `GOOGLE_SERVICE_ACCOUNT_SUBJECT` para delegacion de
dominio.

El adaptador REST solicita los scopes `calendar.events` y `calendar.freebusy`. Los
tokens solo se envian en el header `Authorization` de las llamadas HTTP.

## API utilizada

- `POST /freeBusy` para consultar todos los calendarios configurados.
- `GET /calendars/{calendarId}/events` con `singleEvents`, `showDeleted=false`, rango
  y dos filtros `privateExtendedProperty` para el marcador y paciente. Las consultas
  normales no exponen tombstones de eventos cancelados.
- `POST /calendars/{calendarId}/events` para crear una cita.
- `PATCH /calendars/{calendarId}/events/{eventId}` para mover o cancelar una cita.

`reschedule_appointment` primero recupera el evento por su ID externo y valida sus
propiedades privadas. Si el evento pertenece al paciente pero esta cancelado, la
operacion termina con `InvalidAppointmentState` incluso cuando Google no devuelve
sus fechas. Para un evento activo consulta `freeBusy` solo en el calendario donde
vive la cita, excluye su propio intervalo cuando corresponde y aplica el `PATCH` de
inicio y fin; si el nuevo intervalo esta ocupado no se envia ningun `PATCH`.

La cancelacion usa `status=cancelled` y no borra el evento. Las mutaciones usan
`sendUpdates=all`; como el adaptador no agrega asistentes, esto no envia una
notificacion al paciente y evita la perdida de eventos advertida por Google para
`sendUpdates=none`. La disponibilidad trata cualquier periodo `busy` como bloqueado.
La reserva vuelve a consultar disponibilidad antes de insertar, igual que el fake;
la coordinacion entre procesos queda fuera de este corte.

## Traduccion y aislamiento

Solo los eventos con `managed_by=whatsapp_chatbot` y el `patient_id` esperado se
traducen a `Appointment`. La instancia conserva el `PatientScope` recibido, incluido
el numero de WhatsApp y la conversacion, en lugar de reconstruirlo desde Google.
Los errores de red, timeout, autenticacion y respuestas invalidas se reducen a
`CalendarProviderUnavailable` o `CalendarProviderError`; la busqueda de eventos
ocultos conserva `AppointmentNotFound` y `AppointmentAccessDenied`, mientras que
un evento administrado del paciente con estado no modificable conserva
`InvalidAppointmentState`. La respuesta de cancelacion se valida: si Google omite
campos del recurso, se conserva el intervalo conocido y se fuerza el estado
`cancelled`; si responde explicitamente con otro estado, la operacion falla sin
sincronizar una cancelacion falsa.

El cliente `httpx.AsyncClient` se puede inyectar en pruebas. La suite usa
`httpx.MockTransport`, por lo que no consume APIs ni requiere secretos.
