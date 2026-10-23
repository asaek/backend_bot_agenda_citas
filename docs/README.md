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
- [Disparador compartido de avisos al doctor para chat y voz](./verification/2026-10-22-shared-doctor-notifications.md)
- [Diagnostico de la ventana de entrega al doctor y error 131047](./verification/2026-10-22-whatsapp-doctor-delivery-window.md)
- [Auditoria de destinatarios y numero compartido entre paciente y doctor](./verification/2026-10-22-doctor-notification-routing.md)
- [Configuracion de plantilla y captura diferida de avisos al doctor](./verification/2026-10-22-doctor-template-configuration.md)
- [Envio por plantilla con mapeo explicito y snapshots de reintento](./verification/2026-10-22-doctor-template-delivery.md)
- [Recuperacion de pendientes, espera durable y conciliacion de avisos](./verification/2026-10-22-doctor-notification-retries.md)
- [Callbacks persistentes de Meta y estados reales de entrega de chat/voz](./verification/2026-10-22-meta-delivery-statuses.md)
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
- [Verificacion de aclaracion conservadora del nombre completo](./verification/2026-10-08-patient-name-clarification.md)
- [Recuperacion de envio de WhatsApp por token vencido](./verification/2026-10-08-whatsapp-token-expiration.md)
- [Verificacion de copia completa de .env en local to raspberry](./verification/2026-10-08-local-to-raspberry-full-env.md)
- [Verificacion de reintentos seguros y recuperacion de autenticacion](./verification/2026-10-08-safe-webhook-retries.md)
- [Local to raspberry y cierre de autenticacion de WhatsApp](./verification/2026-10-08-local-to-raspberry-retry-auth-recovery.md)
- [Verificacion de motivos generales y aclaraciones diferenciadas](./verification/2026-10-09-general-appointment-reasons.md)
- [Verificacion de hora de reprogramacion no disponible](./verification/2026-10-09-unavailable-reschedule-time.md)
- [Verificacion de seleccion natural de reprogramacion](./verification/2026-10-09-natural-reschedule-selection.md)
- [Verificacion de nombre unico por reserva y respuestas conversacionales](./verification/2026-10-10-booking-name-continuity.md)
- [Verificacion de seleccion con puntuacion y horarios no disponibles](./verification/2026-10-10-booking-slot-selection.md)
- [Verificacion de una confirmacion de cancelacion y recuperacion de autenticacion](./verification/2026-10-10-single-cancellation-confirmation.md)
- [Etapa 1 de confirmacion natural y aclaracion de reprogramacion](./verification/2026-10-12-natural-reschedule-stage-one.md)
- [Seleccion hibrida de horarios y cierre de autenticacion Meta](./verification/2026-10-12-hybrid-slot-selection.md)
- [Disponibilidad con solo la hora de inicio y despliegue en Raspberry Pi](./verification/2026-10-14-start-only-availability-lists.md)
- [Listados y confirmaciones de citas con solo el inicio y AM/PM](./verification/2026-10-14-start-only-appointment-times.md)
- [Confirmacion al paciente con bloques compartidos de cita y paciente](./verification/2026-10-14-patient-appointment-confirmation.md)

## Funcionalidad especificada, pendiente de implementacion

- [021 - Llamadas entrantes de WhatsApp](./specs/021-whatsapp-inbound-calling/spec.md)
  — laboratorio de audio/Realtime implementado; Calling y continuidad operativa pendientes.
- [Diseno de llamadas](./specs/021-whatsapp-inbound-calling/design.md) y
  [tareas por cortes](./specs/021-whatsapp-inbound-calling/tasks.md).
- [ADR 0054 - Autorizacion ligada al origen](./decisions/0054-inbound-calling-with-scoped-confirmation.md)
  — propuesta, no adoptada por el runtime.
- [ADR 0061 - Contexto historico y apertura independiente de llamadas de laboratorio](./decisions/0061-laboratory-history-and-call-boundaries.md)
  — adopcion parcial para voz y mensajes de `/lab`: apertura aislada CA-22
  implementada y consulta historica CA-26 disponible; contexto reciente enriquecido pendiente.

## Laboratorio de audio implementado

- [ADR 0055 - aiortc y laboratorio aislado](./decisions/0055-isolated-aiortc-audio-laboratory.md).
- [Verificacion en Raspberry Pi](./verification/2026-10-18-aiortc-audio-laboratory.md):
  Opus bidireccional, cliente Chromium, cierre, CPU y memoria.
- [Cliente y conectividad LAN entre computadora y Pi](./verification/2026-10-18-webrtc-client-lan.md):
  HTTP separado de ICE/RTP, Chrome en macOS, host/UDP sin STUN/TURN. Pendiente
  escucha humana y microfono real.
- [ADR 0056 - Voz nativa OpenAI Realtime](./decisions/0056-native-realtime-voice-laboratory.md).
- [Verificacion de voz nativa y herramientas de laboratorio](./verification/2026-10-19-native-realtime-voice.md):
  Chrome/Mac -> Pi -> OpenAI, transcripcion asincrona, consulta de disponibilidad,
  confirmaciones con dobles y 431 tests; escucha/microfono humanos pendientes.
- [ADR 0057 - Continuidad ficticia entre voz y texto](./decisions/0057-laboratory-voice-text-continuity.md).
- [ADR 0058 - Google Calendar opcional para el laboratorio Realtime](./decisions/0058-google-calendar-for-realtime-laboratory.md):
  selector fake/Google, propietario separado de WhatsApp y cliente HTML conservado.
- [ADR 0059 - Sesiones ilimitadas temporalmente en el laboratorio de voz](./decisions/0059-unlimited-voice-lab-sessions.md):
  `VOICE_MAX_SESSIONS=unlimited` solo para pruebas en la Pi; el default permanece en 5.
- [ADR 0060 - Confirmacion explicita tras turnos VAD intermedios](./decisions/0060-explicit-voice-confirmation-after-vad-turns.md):
  admite una secuencia posterior solo con afirmacion clara ligada al turno vigente.
- [Verificacion de interrupciones, confirmaciones e historial compartido](./verification/2026-10-19-voice-text-controls.md):
  445 tests, UI sin APIs y Chrome/Mac con OpenAI real; texto durante llamada y despues de colgar.
- [Hito Realtime, rendimiento y presupuesto](./verification/2026-10-20-realtime-milestone.md):
  453 tests, latencias/recursos/costo y laboratorio Mac/Pi disponible para prueba humana.
- [Recuperacion de reserva tras interrumpir la pregunta](./verification/2026-10-20-interrupted-booking-confirmation.md):
  causa observada, regresion de voz y nueva confirmacion conservando datos.
- [Limite de cinco minutos para llamadas Realtime](./verification/2026-10-20-realtime-five-minute-limit.md):
  maximo de sesion ampliado, con inactividad y cuota sin cambios.
- [Google Calendar en el laboratorio Realtime](./verification/2026-10-20-voice-google-calendar.md):
  causa de agenda falsa, proveedor Google optativo, aislamiento de eventos y runtime verificado.
- [Cuota agotada de sesiones de voz](./verification/2026-10-20-voice-session-quota.md):
  causa del rechazo de llamadas, limite persistente 5/5 y respuesta HTTP 429 accionable.
- [Modo ilimitado del perfil de pruebas](./verification/2026-10-20-unlimited-voice-sessions.md):
  configuración explícita en la Pi, límites de llamada conservados y cuota diaria pendiente.
- [Recuperacion de confirmacion tras turnos VAD cancelados](./verification/2026-10-20-voice-confirmation-turn-sequence.md):
  diagnostico del rechazo repetido y renovacion segura de la pregunta.
- [Confirmacion de reprogramacion tras turnos VAD intermedios](./verification/2026-10-20-reschedule-confirmation-vad-loop.md):
  reproduccion del ciclo y confirmacion solo con transcripcion afirmativa del turno actual.
- [Formato de fecha en confirmaciones habladas](./verification/2026-10-21-voice-mexican-date-format.md):
  hora AM/PM primero, seguida de la fecha `DD/MM/YYYY`; regresion y recarga verificadas.
- [Saludo aislado y continuidad de voz/texto](./verification/2026-10-21-isolated-voice-greeting.md):
  entrada vacia, herramientas deshabilitadas e interrupcion; contexto enriquecido pendiente.
- [Consulta historica acotada de voz/texto](./verification/2026-10-21-voice-history-search.md):
  filtros por tema/fecha/canal, aislamiento y preservacion de propuestas y preguntas.

## Funcionalidad implementada y verificada por cortes

- [011 - Notificaciones al doctor](./specs/011-doctor-notifications/spec.md)
- [012 - Confirmacion de cambios de citas](./specs/012-appointment-change-confirmation/spec.md)
- [013 - Motivo antes de crear una cita](./specs/013-appointment-reason-collection/spec.md)
- [014 - Horarios libres antes de elegir una cita](./specs/014-date-only-availability/spec.md)
- [015 - Diagnostico seguro de errores en modo debug](./specs/015-debug-error-reporting/spec.md)
- [016 - Enrutamiento de intencion con flujos pendientes](./specs/016-conversation-intent-routing/spec.md)
- [017 - Espejo de proyecto y configuracion en Raspberry Pi](./specs/017-local-to-raspberry/spec.md)
- [018 - Reintentos de webhook sin reabrir gestiones antiguas](./specs/018-safe-webhook-retries/spec.md)
- [019 - Seleccion hibrida de horarios](./specs/019-hybrid-slot-selection/spec.md)
- [020 - Confirmacion de cita para el paciente](./specs/020-patient-appointment-confirmation/spec.md)
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
- [ADR 0045 - Aclarar el nombre sospechoso sin corregirlo](./decisions/0045-confirm-suspicious-patient-name.md)
- [ADR 0046 - Copiar .env completo en local to raspberry](./decisions/0046-full-env-in-local-to-raspberry.md)
- [ADR 0047 - Preparar respuestas antes de reintentar WhatsApp](./decisions/0047-persist-replies-before-whatsapp-retries.md)
- [ADR 0048 - Motivos generales comprensibles y aclaraciones diferenciadas](./decisions/0048-understandable-general-appointment-reasons.md)
- [ADR 0050 - Interpretacion hibrida de la seleccion pendiente](./decisions/0050-hybrid-pending-slot-selection.md)
- [ADR 0051 - Solo la hora de inicio en listas de disponibilidad](./decisions/0051-start-only-availability-lists.md)
- [ADR 0052 - Solo el inicio con AM/PM en las horas de citas del paciente](./decisions/0052-start-only-patient-appointment-times.md)
- [ADR 0053 - Bloques compartidos de cita y paciente en confirmaciones](./decisions/0053-shared-appointment-confirmation-blocks.md)
