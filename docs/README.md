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
- [Verificacion de horarios libres antes de agendar](./verification/2026-09-24-date-only-availability.md)
- [Verificacion de variantes de lenguaje para horarios](./verification/2026-09-25-date-only-availability-language.md)

## Funcionalidad implementada y verificada por cortes

- [011 - Notificaciones al doctor](./specs/011-doctor-notifications/spec.md)
- [012 - Confirmacion de cambios de citas](./specs/012-appointment-change-confirmation/spec.md)
- [013 - Motivo antes de crear una cita](./specs/013-appointment-reason-collection/spec.md)
- [014 - Horarios libres antes de elegir una cita](./specs/014-date-only-availability/spec.md)
- [ADR 0019 - Entrega de notificaciones al doctor](./decisions/0019-doctor-notification-delivery.md)
- [ADR 0020 - Formato de respuestas compatible con WhatsApp](./decisions/0020-whatsapp-compatible-response-format.md)
