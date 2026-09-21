# Diseno - Integracion del ToolExecutor

## Estado

Implementado y verificado con proveedores falsos.

## Composicion

```text
main.py
    |
    +-- CalendarProvider = FakeCalendarProvider
    +-- BusinessHours (UTC, lunes-viernes, 09:00-17:00)
    +-- ToolExecutor(provider, business_hours)
    |
    v
ConversationService(llm_provider, tool_executor)
    |
    v
AgentOrchestrator
    |
    +-- ToolCall -> ToolRequest + PatientScope
    +-- ToolExecutor -> ToolResult
    +-- LLM -> respuesta final
```

`main.py` conserva el proveedor y el ejecutor en `app.state` para que varias
solicitudes del proceso compartan el proveedor falso en memoria. Una prueba puede
reemplazar `app.state.tool_executor` o entregar otro ejecutor al factory.

## Responsabilidades

`main.py` es la raiz de composicion: elige `FakeCalendarProvider`, crea el
horario laboral y construye `ToolExecutor`. No interpreta argumentos de
herramientas.

`ConversationService` conserva el `PatientScope`, recibe el ejecutor y construye
`AgentOrchestrator` cuando tambien existe un proveedor LLM. El orquestador crea
`ToolRequest`, por lo que el LLM nunca controla el paciente ni el calendario.

`ToolExecutor` parsea, valida y despacha contra `CalendarProvider`. Las reglas de
`BusinessHours` y las demas validaciones se ejecutan antes de la operacion del
proveedor.

## Sustitucion futura

La funcion `create_calendar_provider()` es el punto de reemplazo para Google
Calendar. El resto del flujo no debe conocer credenciales ni detalles de esa
integracion.
