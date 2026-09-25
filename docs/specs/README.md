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
