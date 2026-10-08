# Documentacion del proyecto

Esta carpeta contiene las decisiones, especificaciones y planes que guian la
implementacion del chatbot de WhatsApp.

## Flujo SDD

Cada funcionalidad se desarrolla siguiendo este orden:

1. `spec.md`: define el problema, el alcance y los criterios de aceptacion.
2. `design.md`: describe la solucion tecnica acordada.
3. `tasks.md`: divide el trabajo en pasos verificables.
4. Implementacion.
5. Verificacion contra los criterios de aceptacion.

La implementacion no debe comenzar hasta que la especificacion y el diseno
esten aprobados.

## Estados

- **Borrador**: todavia contiene preguntas o decisiones abiertas.
- **Aprobado**: el alcance y el diseno fueron confirmados.
- **Implementado**: el codigo fue terminado.
- **Verificado**: los criterios de aceptacion fueron comprobados.

## Indice

- [Lenguaje del dominio](../CONTEXT.md)
- [Proyecto](./project.md)
- [Arquitectura](./architecture.md)
- [Convenciones](./conventions.md)
- [Especificaciones](./specs/README.md)
- [Decisiones](./decisions/README.md)
- [Verificaciones](./verification/2026-09-21-whatsapp-check-availability.md)
- [Verificacion del webhook y notificaciones al doctor](./verification/2026-09-22-doctor-notifications-webhook.md)
- [Verificacion de sincronizacion de Google Calendar](./verification/2026-09-24-google-calendar-event-sync.md)
- [Verificacion del motivo antes de agendar](./verification/2026-09-24-appointment-reason.md)
- [Verificacion de validacion minima del motivo](./verification/2026-09-25-appointment-reason-validation.md)
- [Verificacion de evaluacion estructurada del motivo](./verification/2026-09-25-structured-reason-evaluation.md)
- [Verificacion de señales de prioridad y flujo del motivo](./verification/2026-09-25-priority-signals-and-reason-flow.md)
- [Verificacion del nombre del paciente antes de agendar](./verification/2026-09-26-patient-name-before-booking.md)
- [Verificacion del nombre en cada cita nueva](./verification/2026-10-01-patient-name-every-booking.md)
- [Verificacion de seleccion de horario controlada por el backend](./verification/2026-09-26-backend-slot-selection.md)
- [Verificacion de continuacion de fecha y diagnostico LLM](./verification/2026-09-29-booking-date-and-llm-diagnostics.md)
- [Verificacion de citas ingresadas manualmente en Google Calendar](./verification/2026-09-29-manual-calendar-appointments.md)
- [Verificacion de horarios libres antes de agendar](./verification/2026-09-24-date-only-availability.md)
- [Verificacion de variantes de lenguaje para horarios](./verification/2026-09-25-date-only-availability-language.md)
- [Verificacion de confirmaciones naturales de citas](./verification/2026-10-01-natural-appointment-confirmations.md)
- [Verificacion del diagnostico debug limitado](./verification/2026-10-03-debug-error-reporting.md)
- [Verificacion de resolucion previa a confirmar una reprogramacion](./verification/2026-10-04-reschedule-appointment-lookup.md)
- [Verificacion de horarios disponibles para reprogramar](./verification/2026-10-05-reschedule-availability.md)
- [Verificacion de enrutamiento entre flujos pendientes](./verification/2026-10-05-conversation-intent-routing.md)
- [Verificacion de señales de ojos rojos](./verification/2026-10-05-red-eye-priority-signals.md)
- [Verificacion de disponibilidad antes de pedir hora para reprogramar](./verification/2026-10-05-reschedule-before-time-selection.md)
- [Verificacion de seleccion del proveedor LLM](./verification/2026-10-06-llm-provider-selection.md)
- [Verificacion de prioridad semantica del motivo e historial actual](./verification/2026-10-07-semantic-priority-signals.md)
- [Verificacion de listas en 12 horas con AM/PM](./verification/2026-10-07-twelve-hour-lists.md)
- [Verificacion del reinicio obligatorio en local to raspberry](./verification/2026-10-07-local-to-raspberry-restart.md)
- [Diagnostico de falta de respuesta por token de WhatsApp vencido](./verification/2026-10-07-whatsapp-token-expiration.md)
- [Verificacion de continuidad y pausa persistente de gestiones](./verification/2026-10-07-conversation-pause-continuity.md)

## Funcionalidad implementada y verificada por cortes

- [011 - Notificaciones al doctor](./specs/011-doctor-notifications/spec.md)
- [012 - Confirmacion de cambios de citas](./specs/012-appointment-change-confirmation/spec.md)
- [013 - Motivo antes de crear una cita](./specs/013-appointment-reason-collection/spec.md)
- [014 - Horarios libres antes de elegir una cita](./specs/014-date-only-availability/spec.md)
- [015 - Diagnostico seguro de errores en modo debug](./specs/015-debug-error-reporting/spec.md)
- [016 - Enrutamiento de intencion con flujos pendientes](./specs/016-conversation-intent-routing/spec.md)
- [ADR 0019 - Entrega de notificaciones al doctor](./decisions/0019-doctor-notification-delivery.md)
- [ADR 0020 - Formato de respuestas compatible con WhatsApp](./decisions/0020-whatsapp-compatible-response-format.md)
- [ADR 0027 - Señales de prioridad sin diagnostico](./decisions/0027-priority-signals-without-diagnosis.md)
- [ADR 0028 - Nombre del paciente antes de agendar](./decisions/0028-patient-name-before-booking.md)
- [ADR 0029 - Seleccion de disponibilidad controlada por el backend](./decisions/0029-backend-owned-availability-selection.md)
- [ADR 0030 - Continuacion de fecha de reserva controlada por el backend](./decisions/0030-backend-owned-booking-date.md)
- [ADR 0031 - Asociacion segura de citas manuales por WhatsApp](./decisions/0031-manual-calendar-appointment-ownership.md)
- [ADR 0032 - Solicitud del nombre en cada cita nueva](./decisions/0032-patient-name-for-every-appointment.md)
- [ADR 0037 - Confirmacion de citas por intencion afirmativa o negativa](./decisions/0037-natural-appointment-confirmations.md)
- [ADR 0038 - Diagnostico de errores limitado por modo y remitente](./decisions/0038-debug-error-reporting.md)
- [ADR 0039 - Resolver la cita antes de solicitar confirmacion](./decisions/0039-resolve-appointment-before-confirmation.md)
- [ADR 0040 - Consultar disponibilidad antes de confirmar una reprogramacion](./decisions/0040-reschedule-availability-before-confirmation.md)
- [ADR 0041 - Priorizar la intencion mas reciente sobre flujos pendientes](./decisions/0041-prioritize-current-intent.md)
- [ADR 0042 - Mostrar disponibilidad al solicitar cambiar la hora](./decisions/0042-show-availability-before-reschedule-time.md)
- [ADR 0043 - Seleccion del proveedor OpenAI-compatible por entorno](./decisions/0043-openai-compatible-provider-selection.md)
- [ADR 0044 - Pausa persistente y seleccion contextual de horarios](./decisions/0044-persistent-conversation-pause.md)
