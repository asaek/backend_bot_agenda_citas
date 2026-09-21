# 0013 - Orquestacion limitada de herramientas

## Estado

Aceptada e implementada con `ToolExecutor` inyectado.

## Contexto

El contrato LLM ya puede devolver un `ToolCall` y el backend ya puede ejecutar un
`ToolRequest`, pero faltaba coordinar el ida y vuelta sin que el modelo escogiera
el paciente o el calendario. Un ciclo sin limite podria repetir llamadas
indefinidamente.

## Decision

Se implementa `AgentOrchestrator` como un bucle acotado que recibe los mensajes
del contexto y un `PatientScope` del backend. Convierte cada llamada valida en un
`ToolRequest`, ejecuta el `ToolExecutor`, agrega el `ToolResult` como mensaje
`tool` y vuelve a consultar el LLM hasta obtener texto.

El `ToolExecutor` se inyecta y el limite de llamadas se configura mediante
`LLM_MAX_TOOL_ITERATIONS`, con valor predeterminado 3. Los resultados se sanean
antes de volver al LLM para excluir identificadores de paciente y calendario.

Si el limite se agota, el orquestador lanza un error controlado. Si una llamada
incluye campos reservados, `ToolRequest` la rechaza y el error seguro vuelve al
LLM; nunca se reemplaza el `PatientScope` del backend.

## Consecuencias

- El flujo puede ejecutar herramientas y recibir una redaccion final.
- El proveedor de calendario no queda fijado en el orquestador.
- Un modelo no puede cambiar el paciente o calendario objetivo mediante JSON.
- El sistema necesita un proveedor de calendario inyectado para activar el ciclo
  en runtime.

## Alternativas descartadas

- Ejecutar herramientas directamente desde `main.py`.
- Permitir que el LLM construya el `PatientScope`.
- Repetir llamadas sin un limite de iteraciones.
- Enviar al LLM los objetos internos completos de agenda.
