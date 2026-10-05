# Decisiones arquitectonicas

Esta carpeta conserva decisiones importantes cuyo contexto podria no ser
evidente al revisar solamente el codigo.

Las decisiones se numeran secuencialmente con cuatro digitos. Una decision no
se modifica para ocultar un cambio posterior; si se reemplaza, se crea otra que
indique cual decision anterior queda obsoleta.

## Indice

- [0001 - Backend con Python y FastAPI](./0001-backend-stack.md)
- [0002 - SQLite para la persistencia del MVP](./0002-sqlite-for-persistence-mvp.md)
- [0003 - Contrato de proveedor LLM](./0003-llm-provider.md)
- [0004 - Fake LLM para pruebas automatizadas](./0004-fake-llm-for-automated-tests.md)
- [0005 - Frontera del dominio de citas y herramientas](./0005-calendar-domain-boundary.md)
- [0006 - Contratos tipados para herramientas de calendario](./0006-calendar-tool-contracts.md)
- [0007 - Validacion de herramientas antes del proveedor](./0007-pre-provider-tool-validation.md)
- [0008 - Errores publicos para las herramientas de agenda](./0008-public-calendar-errors.md)
- [0009 - Proveedor falso determinista de calendario](./0009-fake-calendar-provider.md)
- [0010 - Frontera interna del ejecutor de herramientas](./0010-tool-executor-boundary.md)
- [0011 - Alcance del paciente resuelto por el backend](./0011-backend-owned-patient-scope.md)
- [0012 - Respuesta tipada de tool calling](./0012-llm-tool-calling-response.md)
- [0013 - Orquestacion limitada de herramientas](./0013-agent-tool-orchestration.md)
- [0014 - Composicion del runtime con FakeCalendarProvider](./0014-fake-calendar-runtime-composition.md)
- [0015 - Adaptador REST de Google Calendar](./0015-google-calendar-rest-adapter.md)
- [0016 - Identidad local y sincronizacion de citas](./0016-appointment-identity-persistence.md)
- [0017 - Esquemas de herramientas en solicitudes LLM](./0017-llm-tool-schemas.md)
- [0018 - Migracion incremental del proveedor de disponibilidad](./0018-incremental-availability-provider.md)
- [0019 - Entrega de notificaciones al doctor](./0019-doctor-notification-delivery.md)
- [0020 - Formato de respuestas compatible con WhatsApp](./0020-whatsapp-compatible-response-format.md)
- [0021 - Contexto temporal confiable para la agenda](./0021-relative-date-context.md)
- [0022 - Sincronizacion y listados de Google Calendar](./0022-google-calendar-event-sync.md)
- [0023 - Motivo de cita controlado por el backend](./0023-backend-owned-appointment-reason.md)
- [0024 - Disponibilidad antes de elegir la hora](./0024-date-only-availability-before-booking.md)
- [0025 - Validacion minima del motivo de cita](./0025-appointment-reason-minimum-validation.md)
- [0026 - Evaluacion estructurada del motivo de cita](./0026-structured-appointment-reason-evaluation.md)
- [0027 - Señales de prioridad sin diagnostico](./0027-priority-signals-without-diagnosis.md)
- [0028 - Nombre del paciente antes de agendar](./0028-patient-name-before-booking.md)
- [0029 - Seleccion de disponibilidad controlada por el backend](./0029-backend-owned-availability-selection.md)
- [0030 - Continuacion de fecha de reserva controlada por el backend](./0030-backend-owned-booking-date.md)
- [0031 - Asociacion segura de citas manuales por WhatsApp](./0031-manual-calendar-appointment-ownership.md)
- [0032 - Solicitud del nombre en cada cita nueva](./0032-patient-name-for-every-appointment.md)
- [0033 - Valores nulos para el rango opcional de citas](./0033-nullable-appointment-list-range.md)
- [0034 - Bloques para presentar citas en WhatsApp](./0034-appointment-list-block-format.md)
- [0035 - Negrita compatible con WhatsApp en citas](./0035-whatsapp-bold-appointment-labels.md)
- [0036 - Normalizacion del bloque de motivo de cita](./0036-normalize-appointment-reason-line.md)
- [0037 - Confirmacion de citas por intencion afirmativa o negativa](./0037-natural-appointment-confirmations.md)
- [0038 - Diagnostico de errores limitado por modo y remitente](./0038-debug-error-reporting.md)
- [0039 - Resolver la cita antes de solicitar confirmacion](./0039-resolve-appointment-before-confirmation.md)
- [0040 - Consultar disponibilidad antes de confirmar una reprogramacion](./0040-reschedule-availability-before-confirmation.md)
