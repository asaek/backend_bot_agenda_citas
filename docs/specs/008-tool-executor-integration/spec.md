# 008 - Integracion del ToolExecutor

## Estado

Implementado y verificado con `FakeCalendarProvider`, `FakeLLMProvider` y el
webhook HTTP. Google Calendar queda fuera de este corte.

## Objetivo

Activar el ciclo de herramientas en el runtime del backend con una composicion
determinista que no dependa de servicios externos.

## Alcance

- Crear un `CalendarProvider` mediante `FakeCalendarProvider`.
- Configurar `BusinessHours` de lunes a viernes, de 09:00 a 17:00 UTC.
- Crear un `ToolExecutor` con el proveedor y el horario del backend.
- Entregar el `ToolExecutor` a `ConversationService`.
- Hacer que `ConversationService` construya el `AgentOrchestrator` con el LLM y
  el ejecutor recibidos.
- Ejecutar `ToolRequest` con `PatientScope` backend durante el ciclo del agente.
- Permitir reemplazar el proveedor en pruebas sin cambiar la logica del agente.

## Requisitos funcionales

### RF-801 - Composicion del runtime

`main.py` debe crear un `CalendarProvider`, `BusinessHours` y `ToolExecutor` al
iniciar la aplicacion. El proveedor inicial debe ser `FakeCalendarProvider`.

### RF-802 - Uso desde ConversationService

`ConversationService` debe recibir el `ToolExecutor`, construir el orquestador y
usarlo cuando el LLM devuelva un `ToolCall`.

### RF-803 - Alcance y validacion

El `AgentOrchestrator` debe convertir la llamada en `ToolRequest` con el
`PatientScope` del contexto. Las reglas de `BusinessHours` deben ejecutarse antes
del proveedor.

### RF-804 - Sustitucion del proveedor

La composicion debe aceptar otro `CalendarProvider` por inyeccion para pruebas y
para la futura integracion con Google Calendar.

## Criterios de aceptacion

1. El runtime expone un `FakeCalendarProvider` y un `ToolExecutor` configurado.
2. `ConversationService` usa el ejecutor y solicita una respuesta final despues
   del `ToolResult`.
3. El `PatientScope` de WhatsApp llega al `ToolRequest` y no al JSON del LLM.
4. Una solicitud fuera de `BusinessHours` devuelve un resultado seguro.
5. El webhook completa el ciclo con dos turnos del LLM sin servicios externos.
6. Un proveedor alternativo puede inyectarse en la misma composicion.

## Fuera del alcance

- Implementar Google Calendar.
- Leer horarios laborales desde una configuracion externa.
- Persistir citas del `FakeCalendarProvider` en SQLite.
- Permitir varias llamadas paralelas en una respuesta.
