# 0012 - Respuesta tipada de tool calling

## Estado

Aceptada e implementada para el contrato del proveedor LLM.

## Contexto

El proveedor actual devuelve solamente texto, pero el agente necesita expresar
una solicitud estructurada de agenda. Los argumentos de esa solicitud son datos
no confiables del LLM y no deben confundirse con el alcance confiable del
paciente.

## Decision

`LLMProvider.generate()` devuelve `LLMResponse`, una union de texto y `ToolCall`.
`ToolCall` contiene un nombre y un mapa de argumentos. El adaptador compatible con
OpenAI normaliza una llamada nativa de tipo `function` y tambien acepta la forma
interna `tool_call` para pruebas y adaptadores.

La capa del proveedor valida solo la estructura basica: nombre no vacio,
argumentos objeto, JSON valido y como maximo una llamada. La validacion de
argumentos de agenda, la inyeccion de `PatientScope` y la ejecucion pertenecen al
backend.

Mientras el ejecutor no esta conectado, el webhook registra `UnsupportedToolCall`
y envia la respuesta controlada. Nunca envia la representacion de `ToolCall` al
paciente.

## Consecuencias

- El consumidor puede distinguir texto de una operacion solicitada.
- El contrato no ata la logica conversacional a un proveedor concreto.
- La identidad del paciente permanece fuera de la respuesta del LLM.
- La ejecucion requiere un incremento posterior y no se simula como texto.

## Alternativas descartadas

- Devolver un diccionario sin tipo desde `LLMProvider`.
- Codificar tool calls dentro del texto que se envia al paciente.
- Permitir que el LLM incluya `patient_id`, `conversation_id` o
  `whatsapp_number` en el alcance de la herramienta.
