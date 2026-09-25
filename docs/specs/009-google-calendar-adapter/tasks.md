# Tareas - Adaptador de Google Calendar

## Implementacion

- [x] Anadir `GoogleCalendarProvider` compatible con `CalendarProvider`.
- [x] Anadir autenticacion OAuth y cuenta de servicio mediante `google-auth`.
- [x] Consultar `freeBusy` para uno o varios calendarios.
- [x] Crear, listar, reprogramar y cancelar eventos con propiedades privadas.
- [x] Seguir paginas de `events.list` y traducir eventos a `Appointment`.
- [x] Seleccionar fake o Google desde `main.py` sin cambiar el agente.
- [x] Seleccionar Google solo para `check_availability` durante la migracion
  incremental.
- [x] Filtrar slots devueltos por `BusinessHours` antes de exponerlos al agente.

## Pruebas

- [x] Probar disponibilidad y encabezado de autenticacion con `MockTransport`.
- [x] Probar propiedades privadas al crear una cita.
- [x] Probar paginacion, filtro de paciente y preservacion de `PatientScope`.
- [x] Probar reprogramacion, cancelacion, acceso, estados y errores transitorios.
- [x] Probar que un conflicto de `freeBusy` no envia el `PATCH` de reprogramacion.
- [x] Probar la reprogramacion a traves del ID interno persistido y el adaptador Google.
- [x] Probar respuestas parciales y estados invalidos al cancelar un evento Google.
- [x] Probar la cancelacion a traves del ID interno y la sincronizacion del estado local.
- [x] Evitar tombstones cancelados en listados normales y usar `sendUpdates=all` en
  las mutaciones.
- [x] Ejecutar la suite completa en el mirror de Raspberry Pi.

## Fuera de este corte

- [ ] Verificar una cuenta real de Google Calendar con secretos provisionados.
- [ ] Persistir horarios, festivos y bloqueos fuera de la configuracion actual.
