# 0014 - Composicion del runtime con FakeCalendarProvider

## Estado

Aceptada e implementada.

## Contexto

El contrato de agenda, el `ToolExecutor` y el orquestador ya estaban probados de
forma aislada, pero el webhook solo podia usarlos si una dependencia externa
colocaba manualmente un ejecutor en `app.state`. Faltaba una composicion por
defecto para probar el flujo completo sin Google Calendar.

## Decision

`main.py` crea un `FakeCalendarProvider`, un `BusinessHours` determinista de
09:00 a 17:00 UTC de lunes a viernes y un `ToolExecutor`. El ejecutor se conserva
en `app.state` y se entrega a `ConversationService`.

`ConversationService` construye el `AgentOrchestrator` con el proveedor LLM y el
ejecutor recibidos. `AgentOrchestrator` sigue siendo el unico componente que
convierte un `ToolCall` no confiable en `ToolRequest` con `PatientScope` backend.

La funcion `create_calendar_provider()` queda como punto de sustitucion para un
proveedor real sin cambiar el ciclo conversacional.

## Consecuencias

- El webhook ejecuta herramientas en el MVP tecnico sin servicios externos.
- Las citas del proveedor falso viven en memoria del proceso.
- El horario laboral se aplica antes de cualquier operacion del proveedor.
- Google Calendar requiere una decision y una implementacion posteriores.

## Alternativas descartadas

- Crear un proveedor falso dentro de cada webhook y perder su estado.
- Ejecutar `ToolRequest` directamente desde `main.py`.
- Permitir que el LLM seleccione el `CalendarProvider` o el calendario.
