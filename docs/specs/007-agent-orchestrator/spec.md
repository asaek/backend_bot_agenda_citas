# 007 - Orquestador del agente

## Estado

Implementado y verificado con `FakeLLMProvider`, `FakeCalendarProvider` y el
webhook HTTP. El proveedor de calendario se inyecta; Google Calendar queda
pendiente.

## Objetivo

Coordinar el ciclo completo de una conversacion con herramientas sin trasladar
al LLM la identidad del paciente ni la seleccion de calendarios.

## Alcance

- Recibir los mensajes construidos para el LLM y el `PatientScope` del backend.
- Solicitar una respuesta al LLM.
- Convertir un `ToolCall` en `ToolRequest` agregando el `PatientScope`.
- Ejecutar el request mediante `ToolExecutor`.
- Entregar el `ToolResult` al LLM como mensajes estructurados.
- Repetir hasta obtener texto final.
- Limitar el numero de iteraciones de herramientas.
- Ocultar del resultado al LLM los campos de paciente y calendario controlados por
  el backend.

## Requisitos funcionales

### RF-701 - Ciclo de agente

El orquestador debe ejecutar `LLM -> ToolRequest + PatientScope -> ToolExecutor
-> ToolResult -> LLM` y devolver la respuesta textual final.

### RF-702 - Alcance confiable

Cada `ToolRequest` debe recibir el `PatientScope` provisto por el backend. Los
argumentos del `ToolCall` no pueden sustituir `patient_id`, `conversation_id`,
`whatsapp_number` ni el calendario configurado.

### RF-703 - Resultado estructurado

El resultado de la herramienta debe volver al LLM como un mensaje `tool`, junto
con el mensaje `assistant` que representa la llamada. Los detalles internos no
deben filtrarse.

### RF-704 - Iteraciones limitadas

El orquestador debe aceptar un limite positivo y rechazar el ciclo cuando el LLM
solicite otra herramienta despues de alcanzar ese limite.

### RF-705 - Errores de herramientas

Los errores de argumentos o proveedor deben volver como `ToolResult` seguro para
que el LLM pueda redactar una respuesta. No deben propagarse detalles internos.

### RF-706 - Respuesta final

El ciclo solo termina exitosamente con texto. Una llamada no ejecutable o un
limite agotado no se debe enviar como texto al paciente.

## Criterios de aceptacion

1. Una llamada valida se convierte en `ToolRequest` con el `PatientScope` actual.
2. El `ToolExecutor` recibe y ejecuta la solicitud.
3. El segundo turno del LLM recibe el resultado como mensaje `tool`.
4. Una respuesta textual posterior se devuelve como respuesta final.
5. Los argumentos con identificadores de paciente o calendario producen un
   `ToolResult` invalido y no modifican el proveedor.
6. Los resultados enviados al LLM no contienen `patient_scope`, identificadores
   de paciente ni `calendar_id`.
7. El limite impide una llamada adicional y produce un error controlado.
8. El limite se carga desde `LLM_MAX_TOOL_ITERATIONS` y por defecto es 3.
9. La suite funciona sin servicios externos.

## Fuera de alcance

- Implementar Google Calendar.
- Persistir citas en SQLite.
- Permitir varias llamadas en paralelo en una misma respuesta.
- Elegir calendarios desde el LLM.
