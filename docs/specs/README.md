# Especificaciones

Cada funcionalidad vive en una carpeta numerada:

```text
NNN-nombre-de-la-funcionalidad/
├── spec.md
├── design.md
└── tasks.md
```

## Contenido

- `spec.md`: comportamiento observable, alcance y criterios de aceptacion.
- `design.md`: componentes, flujos, interfaces y decisiones tecnicas.
- `tasks.md`: lista ordenada de trabajo y verificaciones.

## Reglas

1. La especificacion describe el resultado, no la implementacion.
2. El diseno debe satisfacer todos los requisitos de la especificacion.
3. Las tareas deben ser pequeñas y verificables.
4. Un cambio de alcance debe reflejarse primero en la especificacion.
5. Una funcionalidad solo se considera terminada cuando cumple sus criterios de
   aceptacion.

## Especificaciones actuales

- [001 - Webhook de WhatsApp](./001-whatsapp-webhook/spec.md)
- [002 - Persistencia y Conversation Service](./002-persistence-conversation-service/spec.md)
- [003 - Agente LLM basico](./003-basic-llm-agent/spec.md)
- [004 - Pruebas automatizadas del ciclo sin API](./004-automated-webhook-tests/spec.md)
- [005 - Contrato de herramientas de citas](./005-tool-contract/spec.md)
- [006 - Contrato de tool calling del LLM](./006-llm-tool-calling/spec.md)
- [007 - Orquestador del agente](./007-agent-orchestrator/spec.md)
- [008 - Integracion del ToolExecutor](./008-tool-executor-integration/spec.md)
- [009 - Adaptador de Google Calendar](./009-google-calendar-adapter/spec.md)
- [010 - Persistencia de citas](./010-appointment-persistence/spec.md)
- [011 - Notificaciones al doctor](./011-doctor-notifications/spec.md)
- [012 - Confirmacion de cambios de citas](./012-appointment-change-confirmation/spec.md)
- [013 - Motivo antes de crear una cita](./013-appointment-reason-collection/spec.md)
- [014 - Horarios libres antes de elegir una cita](./014-date-only-availability/spec.md)
- [015 - Diagnostico seguro de errores en modo debug](./015-debug-error-reporting/spec.md)
- [016 - Enrutamiento de intencion con flujos pendientes](./016-conversation-intent-routing/spec.md)
- [017 - Espejo de proyecto y configuracion en Raspberry Pi](./017-local-to-raspberry/spec.md)
- [018 - Reintentos de webhook sin reabrir gestiones antiguas](./018-safe-webhook-retries/spec.md)
- [019 - Seleccion hibrida de horarios](./019-hybrid-slot-selection/spec.md)
- [020 - Confirmacion de cita para el paciente](./020-patient-appointment-confirmation/spec.md)
- [021 - Llamadas entrantes de WhatsApp](./021-whatsapp-inbound-calling/spec.md)
  — laboratorio A-E implementado y verificado automaticamente en la Pi;
  voz Realtime, agenda Google opcional de laboratorio y continuidad ficticia;
  escucha fisica, identidad operativa e integracion con Meta pendientes. Incluye
  metricas/costo (CA-18), agenda (CA-19), cuota visible (CA-20) y futura cuota diaria (CA-21).
  El contrato de contexto historico y apertura propia de `/lab` (CA-22 a CA-25,
  ADR 0061) tiene adopcion parcial: apertura aislada CA-22 comprobada con dobles;
  consulta de temas antiguos CA-26 disponible; contexto reciente enriquecido pendiente.
