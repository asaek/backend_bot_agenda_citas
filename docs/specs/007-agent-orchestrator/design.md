# Diseno - Orquestador del agente

## Estado

Implementado y verificado con proveedores falsos.

## Flujo

```text
IncomingTextMessage
    |
    v
ConversationContext + PatientScope
    |
    v
ConversationService.build_chat_messages()
    |
    v
AgentOrchestrator
    |
    +-- LLM -> texto -> respuesta final
    |
    +-- LLM -> ToolCall
               |
               v
       ToolRequest + PatientScope
               |
               v
          ToolExecutor
               |
               v
          ToolResult -> mensajes assistant/tool -> LLM
```

## Construccion segura del request

`AgentOrchestrator` recibe el `PatientScope` fuera de los mensajes del LLM. Para
una llamada valida convierte el nombre a `ToolName` y construye `ToolRequest` con
los argumentos no confiables y ese alcance. `ToolRequest` rechaza los campos
reservados; nombres desconocidos y argumentos prohibidos se reducen a
`ToolResult.failure()`.

El calendario no se copia desde el `ToolCall`. `ToolExecutor` lo resuelve a
traves del `CalendarProvider` que recibe por inyeccion.

## Mensajes de ida y vuelta

El orquestador conserva una lista temporal de `ChatMessage`. Despues de ejecutar
una herramienta agrega un mensaje `assistant` con el `ToolCall` estructurado y un
mensaje `tool` con el JSON seguro de `ToolResult`. Los resultados se sanea para no
exponer `patient_scope`, `patient_id`, `conversation_id`, `whatsapp_number` ni
`calendar_id`.

El `ToolCall` recibe un identificador interno cuando el proveedor no lo entrega,
lo que permite relacionar el mensaje `assistant` con el mensaje `tool`.

## Limite

`max_iterations` cuenta llamadas de herramientas, no turnos textuales. Con el
valor 3 se permiten hasta tres ejecuciones y una cuarta respuesta final del LLM.
Si el LLM pide otra herramienta al alcanzar el limite, se lanza
`AgentIterationLimitError`, un `LLMProviderError` que el webhook convierte en la
respuesta controlada.

`ConversationService` acepta el orquestador por inyeccion. Si no existe un
`ToolExecutor` configurado, conserva el camino textual anterior y evita inventar
un proveedor de calendario de produccion.
